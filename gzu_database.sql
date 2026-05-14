-- Служба заказчика ГЖУ: схема БД (PostgreSQL)
-- Кодировка: UTF-8

SET client_encoding = 'UTF8';

-- Удаление в обратном порядке зависимостей (для повторного применения)
DROP TRIGGER IF EXISTS trg_houses_propagate_precinct ON houses;
DROP TRIGGER IF EXISTS trg_apartments_set_precinct_snapshot ON apartments;
DROP TRIGGER IF EXISTS trg_residents_count_ins ON residents;
DROP TRIGGER IF EXISTS trg_residents_count_upd ON residents;
DROP TRIGGER IF EXISTS trg_residents_count_del ON residents;

DROP VIEW IF EXISTS v_precinct_residents_grouped;
DROP VIEW IF EXISTS v_sites_with_multiple_houses;
DROP VIEW IF EXISTS v_apartments_with_house_service;
DROP VIEW IF EXISTS v_services_list;

DROP TABLE IF EXISTS residents CASCADE;
DROP TABLE IF EXISTS apartments CASCADE;
DROP TABLE IF EXISTS houses CASCADE;
DROP TABLE IF EXISTS maintenance_sites CASCADE;
DROP TABLE IF EXISTS service_departments CASCADE;
DROP TABLE IF EXISTS election_precincts CASCADE;
DROP TABLE IF EXISTS tariffs CASCADE;
DROP TABLE IF EXISTS payer_codes CASCADE;
DROP TABLE IF EXISTS services CASCADE;

-- 1. Службы
CREATE TABLE services (
    service_id      SERIAL PRIMARY KEY,
    service_code    VARCHAR(16)  NOT NULL UNIQUE,
    name            VARCHAR(200) NOT NULL CHECK (length(trim(name)) > 0),
    phone           VARCHAR(32)  DEFAULT 'не указан',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_services_name ON services (name);

-- 2. Отделы служб
CREATE TABLE service_departments (
    service_id  INTEGER      NOT NULL REFERENCES services (service_id) ON DELETE CASCADE,
    dept_id     INTEGER      NOT NULL CHECK (dept_id > 0),
    name        VARCHAR(200) NOT NULL,
    address     TEXT         NOT NULL CHECK (length(trim(address)) > 0),
    PRIMARY KEY (service_id, dept_id)
);

CREATE INDEX idx_departments_address ON service_departments (address);

-- 3. Участки (эксплуатационные)
CREATE TABLE maintenance_sites (
    service_id  INTEGER      NOT NULL,
    dept_id     INTEGER      NOT NULL,
    site_id     INTEGER      NOT NULL CHECK (site_id > 0),
    name        VARCHAR(200) NOT NULL,
    PRIMARY KEY (service_id, dept_id, site_id),
    FOREIGN KEY (service_id, dept_id)
        REFERENCES service_departments (service_id, dept_id) ON DELETE CASCADE
);

CREATE INDEX idx_sites_name ON maintenance_sites (name);

-- 4. Избирательные участки (для отчёта по спискам)
CREATE TABLE election_precincts (
    precinct_id     SERIAL PRIMARY KEY,
    precinct_number INTEGER NOT NULL UNIQUE CHECK (precinct_number BETWEEN 1 AND 9999),
    title           VARCHAR(200) NOT NULL DEFAULT 'Участок',
    address         TEXT
);

CREATE INDEX idx_precincts_number ON election_precincts (precinct_number);

-- 5. Шифры плательщика
CREATE TABLE payer_codes (
    code_id          SERIAL PRIMARY KEY,
    code_name        VARCHAR(120) NOT NULL,
    payment_percent  NUMERIC(5,2) NOT NULL DEFAULT 100.00
        CHECK (payment_percent > 0 AND payment_percent <= 100),
    notes            TEXT DEFAULT ''
);

CREATE UNIQUE INDEX idx_payer_codes_name_unique ON payer_codes (lower(code_name));

-- 6. Тарифы (набор признаков квартиры -> ставка за м²)
CREATE TABLE tariffs (
    tariff_id       SERIAL PRIMARY KEY,
    has_cold_water  BOOLEAN NOT NULL DEFAULT FALSE,
    has_hot_water   BOOLEAN NOT NULL DEFAULT FALSE,
    has_garbage_chute BOOLEAN NOT NULL DEFAULT FALSE,
    has_elevator    BOOLEAN NOT NULL DEFAULT FALSE,
    rate_per_sqm    NUMERIC(14,4) NOT NULL CHECK (rate_per_sqm >= 0),
    valid_from      DATE NOT NULL DEFAULT DATE '2024-01-01',
    description     VARCHAR(200) DEFAULT '',
    CONSTRAINT uq_tariff_signature UNIQUE (
        has_cold_water, has_hot_water, has_garbage_chute, has_elevator, valid_from
    )
);

CREATE INDEX idx_tariffs_rate ON tariffs (rate_per_sqm);

-- 7. Дома
CREATE TABLE houses (
    house_id              SERIAL PRIMARY KEY,
    service_id            INTEGER NOT NULL,
    dept_id               INTEGER NOT NULL,
    site_id               INTEGER NOT NULL,
    street                VARCHAR(200) NOT NULL,
    house_number          VARCHAR(32)  NOT NULL,
    building_corpus       VARCHAR(16)  NOT NULL DEFAULT '',
    election_precinct_id INTEGER REFERENCES election_precincts (precinct_id)
        ON DELETE SET NULL,
    FOREIGN KEY (service_id, dept_id, site_id)
        REFERENCES maintenance_sites (service_id, dept_id, site_id),
    CONSTRAINT uq_house_address UNIQUE (street, house_number, building_corpus)
);

CREATE INDEX idx_houses_precinct ON houses (election_precinct_id);
CREATE INDEX idx_houses_street ON houses (street);

-- 8. Квартиры
CREATE TABLE apartments (
    apartment_id       SERIAL PRIMARY KEY,
    house_id           INTEGER NOT NULL REFERENCES houses (house_id) ON DELETE CASCADE,
    apt_number         VARCHAR(16) NOT NULL,
    living_area_sqm    NUMERIC(10,2) NOT NULL CHECK (living_area_sqm >= 0),
    total_area_sqm     NUMERIC(10,2) NOT NULL CHECK (total_area_sqm >= living_area_sqm),
    is_privatized      BOOLEAN NOT NULL DEFAULT FALSE,
    has_cold_water     BOOLEAN NOT NULL DEFAULT TRUE,
    has_hot_water      BOOLEAN NOT NULL DEFAULT FALSE,
    has_garbage_chute  BOOLEAN NOT NULL DEFAULT FALSE,
    has_elevator       BOOLEAN NOT NULL DEFAULT FALSE,
    resident_count     INTEGER NOT NULL DEFAULT 0 CHECK (resident_count >= 0),
    election_precinct_id_snapshot INTEGER REFERENCES election_precincts (precinct_id)
        ON DELETE SET NULL,
    CONSTRAINT uq_apartment_in_house UNIQUE (house_id, apt_number)
);

CREATE INDEX idx_apartments_house ON apartments (house_id);
CREATE INDEX idx_apartments_total_area ON apartments (total_area_sqm);

-- 9. Жильцы
CREATE TABLE residents (
    resident_id        SERIAL PRIMARY KEY,
    apartment_id       INTEGER NOT NULL REFERENCES apartments (apartment_id) ON DELETE CASCADE,
    full_name          VARCHAR(200) NOT NULL,
    inn                VARCHAR(12),
    passport_series_no VARCHAR(32),
    birth_date         DATE NOT NULL CHECK (birth_date < CURRENT_DATE),
    is_primary_tenant  BOOLEAN NOT NULL DEFAULT FALSE,
    payer_code_id      INTEGER REFERENCES payer_codes (code_id) ON DELETE SET NULL,
    CONSTRAINT chk_inn_format CHECK (
        inn IS NULL OR inn ~ '^\d{10}$|^\d{12}$'
    )
);

CREATE INDEX idx_residents_apartment ON residents (apartment_id);
CREATE INDEX idx_residents_name ON residents (full_name);
CREATE INDEX idx_residents_payer ON residents (payer_code_id);

-- ---------------------------------------------------------------------------
-- Представления (VIEW)
-- ---------------------------------------------------------------------------

-- Одна «базовая» таблица + вычисляемое поле в проекции
CREATE VIEW v_services_list AS
SELECT
    service_id,
    service_code,
    name,
    phone,
    (created_at::date) AS registered_on
FROM services;

-- Несколько таблиц: квартира + дом + служба + отдел + участок
CREATE VIEW v_apartments_with_house_service AS
SELECT
    a.apartment_id,
    a.apt_number,
    a.total_area_sqm,
    a.resident_count,
    h.street,
    h.house_number,
    h.building_corpus,
    s.name AS service_name,
    d.name AS department_name,
    m.name AS site_name,
    ep.precinct_number
FROM apartments a
JOIN houses h ON h.house_id = a.house_id
JOIN maintenance_sites m
  ON m.service_id = h.service_id AND m.dept_id = h.dept_id AND m.site_id = h.site_id
JOIN service_departments d
  ON d.service_id = h.service_id AND d.dept_id = h.dept_id
JOIN services s ON s.service_id = h.service_id
LEFT JOIN election_precincts ep ON ep.precinct_id = a.election_precinct_id_snapshot;

-- GROUP BY + HAVING: участки с более чем одним домом
CREATE VIEW v_sites_with_multiple_houses AS
SELECT
    h.service_id,
    h.dept_id,
    h.site_id,
    COUNT(*)::INTEGER AS houses_count
FROM houses h
GROUP BY h.service_id, h.dept_id, h.site_id
HAVING COUNT(*) >= 2;

-- Дополнительно: жильцы по избирательным участкам (агрегация)
CREATE VIEW v_precinct_residents_grouped AS
SELECT
    ep.precinct_id,
    ep.precinct_number,
    ep.title,
    COUNT(r.resident_id) AS residents_total
FROM election_precincts ep
LEFT JOIN houses h ON h.election_precinct_id = ep.precinct_id
LEFT JOIN apartments a ON a.house_id = h.house_id
LEFT JOIN residents r ON r.apartment_id = a.apartment_id
GROUP BY ep.precinct_id, ep.precinct_number, ep.title
HAVING COUNT(r.resident_id) > 0;

-- ---------------------------------------------------------------------------
-- Функции и триггеры: денормализация и «каскад» в связанных строках
-- ---------------------------------------------------------------------------

-- Поддержка resident_count в apartments
CREATE OR REPLACE FUNCTION fn_refresh_apartment_resident_count(p_apartment_id INTEGER)
RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    UPDATE apartments
    SET resident_count = (
        SELECT COUNT(*)::INTEGER FROM residents r WHERE r.apartment_id = p_apartment_id
    )
    WHERE apartment_id = p_apartment_id;
END;
$$;

CREATE OR REPLACE FUNCTION trg_residents_recount()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM fn_refresh_apartment_resident_count(OLD.apartment_id);
    ELSIF TG_OP = 'INSERT' THEN
        PERFORM fn_refresh_apartment_resident_count(NEW.apartment_id);
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.apartment_id IS DISTINCT FROM NEW.apartment_id THEN
            PERFORM fn_refresh_apartment_resident_count(OLD.apartment_id);
        END IF;
        PERFORM fn_refresh_apartment_resident_count(NEW.apartment_id);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER trg_residents_count_ins
    AFTER INSERT ON residents
    FOR EACH ROW EXECUTE PROCEDURE trg_residents_recount();

CREATE TRIGGER trg_residents_count_upd
    AFTER UPDATE ON residents
    FOR EACH ROW EXECUTE PROCEDURE trg_residents_recount();

CREATE TRIGGER trg_residents_count_del
    AFTER DELETE ON residents
    FOR EACH ROW EXECUTE PROCEDURE trg_residents_recount();

-- Снимок избирательного участка на квартире (копия с дома при вставке/смене дома)
CREATE OR REPLACE FUNCTION trg_apartments_sync_precinct_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    pid INTEGER;
BEGIN
    SELECT election_precinct_id INTO pid FROM houses WHERE house_id = NEW.house_id;
    NEW.election_precinct_id_snapshot := pid;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_apartments_set_precinct_snapshot
    BEFORE INSERT OR UPDATE OF house_id ON apartments
    FOR EACH ROW EXECUTE PROCEDURE trg_apartments_sync_precinct_fn();

-- При смене участка у дома — обновить все квартиры (каскад в связанной таблице)
CREATE OR REPLACE FUNCTION trg_houses_propagate_precinct_fn()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.election_precinct_id IS DISTINCT FROM NEW.election_precinct_id THEN
        UPDATE apartments
        SET election_precinct_id_snapshot = NEW.election_precinct_id
        WHERE house_id = NEW.house_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_houses_propagate_precinct
    AFTER UPDATE OF election_precinct_id ON houses
    FOR EACH ROW EXECUTE PROCEDURE trg_houses_propagate_precinct_fn();

COMMENT ON TABLE services IS 'Службы ГЖУ';
COMMENT ON TABLE service_departments IS 'Отделы служб';
COMMENT ON TABLE maintenance_sites IS 'Эксплуатационные участки';
COMMENT ON TABLE election_precincts IS 'Избирательные участки';
COMMENT ON TABLE houses IS 'Дома';
COMMENT ON TABLE apartments IS 'Квартиры';
COMMENT ON TABLE residents IS 'Жильцы';
COMMENT ON TABLE payer_codes IS 'Шифры плательщика (льготы/доли оплаты)';
COMMENT ON TABLE tariffs IS 'Тарифы по набору коммунальных признаков';
-- Демонстрационные данные для службы заказчика ГЖУ

INSERT INTO services (service_code, name, phone) VALUES
    ('GZU-01', 'Служба заказчика ГЖУ Северного округа', '+7 (495) 100-01-01'),
    ('GZU-02', 'Служба заказчика ГЖУ Южного округа', '+7 (495) 200-02-02');

INSERT INTO service_departments (service_id, dept_id, name, address) VALUES
    (1, 1, 'Отдел учёта жилого фонда', 'г. Москва, ул. Лесная, д. 5'),
    (1, 2, 'Отдел договоров', 'г. Москва, ул. Лесная, д. 5, корп. 2'),
    (2, 1, 'Отдел эксплуатации', 'г. Москва, пр-т Андропова, д. 22');

INSERT INTO maintenance_sites (service_id, dept_id, site_id, name) VALUES
    (1, 1, 1, 'Участок №1 (микрорайон А)'),
    (1, 1, 2, 'Участок №2 (микрорайон Б)'),
    (1, 2, 1, 'Участок договорного сопровождения'),
    (2, 1, 1, 'Участок Юг-центр');

INSERT INTO election_precincts (precinct_number, title, address) VALUES
    (101, 'Избирательный участок №101', 'Школа №450, ул. Центральная, 10'),
    (102, 'Избирательный участок №102', 'Дом культуры «Южный», пр. Мира, 3'),
    (205, 'Избирательный участок №205', 'Гимназия №12, ул. Садовая, 7');

INSERT INTO payer_codes (code_name, payment_percent, notes) VALUES
    ('Полная оплата', 100.00, 'Без льгот'),
    ('Ветеран труда', 50.00, 'Региональная льгота'),
    ('Многодетная семья', 30.00, 'По справке'),
    ('Инвалид I группы', 50.00, 'Федеральная льгота');

INSERT INTO tariffs (
    has_cold_water, has_hot_water, has_garbage_chute, has_elevator,
    rate_per_sqm, valid_from, description
) VALUES
    (TRUE,  FALSE, FALSE, FALSE, 45.5000, DATE '2024-01-01', 'ХВ только'),
    (TRUE,  TRUE,  FALSE, FALSE, 78.2000, DATE '2024-01-01', 'ХВ+ГВ'),
    (TRUE,  TRUE,  TRUE,   FALSE, 82.7500, DATE '2024-01-01', 'ХВ+ГВ+мусоропровод'),
    (TRUE,  TRUE,  TRUE,   TRUE,  91.3000, DATE '2024-01-01', 'Полный пакет с лифтом'),
    (TRUE,  FALSE, FALSE, TRUE,  52.1000, DATE '2025-01-01', 'ХВ+лифт (пересмотр тарифов)');

INSERT INTO houses (
    service_id, dept_id, site_id, street, house_number, building_corpus,
    election_precinct_id
) VALUES
    (1, 1, 1, 'ул. Берёзовая', '12', '', 1),
    (1, 1, 1, 'ул. Берёзовая', '12', 'к. 2', 1),
    (1, 1, 2, 'пр. Мира', '3', '', 2),
    (2, 1, 1, 'ул. Садовая', '7', 'стр. 1', 3),
    (1, 1, 1, 'ул. Берёзовая', '20', '', 1);

INSERT INTO apartments (
    house_id, apt_number, living_area_sqm, total_area_sqm, is_privatized,
    has_cold_water, has_hot_water, has_garbage_chute, has_elevator
) VALUES
    (1, '1',  28.5,  42.0, TRUE,  TRUE, TRUE, FALSE, FALSE),
    (1, '2',  31.0,  48.5, FALSE, TRUE, TRUE, TRUE,  FALSE),
    (2, '10', 22.0,  35.0, FALSE, TRUE, FALSE, FALSE, FALSE),
    (3, '5',  40.0,  62.0, TRUE,  TRUE, TRUE, TRUE,  TRUE),
    (4, '1',  18.0,  28.0, FALSE, TRUE, TRUE, FALSE, FALSE),
    (5, '7',  33.5,  50.0, TRUE,  TRUE, TRUE, FALSE, TRUE);

INSERT INTO residents (
    apartment_id, full_name, inn, passport_series_no, birth_date,
    is_primary_tenant, payer_code_id
) VALUES
    (1, 'Иванов Иван Иванович', '1234567890', '4510 112233', DATE '1985-03-12', TRUE, 1),
    (1, 'Иванова Мария Сергеевна', '9876543210', '4511 223344', DATE '1988-07-22', FALSE, 3),
    (2, 'Петров Пётр Петрович', NULL, '4512 334455', DATE '1990-11-01', TRUE, 2),
    (3, 'Сидорова Анна Олеговна', '1122334455', '4513 445566', DATE '1976-05-30', TRUE, 1),
    (4, 'Кузнецов Олег Викторович', NULL, '4514 556677', DATE '2001-01-15', TRUE, 1),
    (4, 'Кузнецова Виктория Олеговна', NULL, '4514 667788', DATE '2003-09-09', FALSE, 1),
    (5, 'Смирнова Елена Павловна', '5566778899', '4515 778899', DATE '1965-12-01', TRUE, 4),
    (6, 'Фёдоров Фёдор Фёдорович', NULL, '4516 889900', DATE '1995-04-18', TRUE, 1);
