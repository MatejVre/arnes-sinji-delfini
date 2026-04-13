BEGIN TRANSACTION;

INSERT OR IGNORE INTO groups(name) VALUES ('finance');
INSERT OR IGNORE INTO groups(name) VALUES ('hr');
INSERT OR IGNORE INTO groups(name) VALUES ('law');

INSERT OR IGNORE INTO users(name, password_hash) VALUES ('šef', '__PASSWORD_HASH__');
INSERT OR IGNORE INTO users(name, password_hash) VALUES ('finance', '__PASSWORD_HASH__');
INSERT OR IGNORE INTO users(name, password_hash) VALUES ('hr', '__PASSWORD_HASH__');
INSERT OR IGNORE INTO users(name, password_hash) VALUES ('law', '__PASSWORD_HASH__');

UPDATE users
SET password_hash = '__PASSWORD_HASH__'
WHERE name IN ('šef', 'finance', 'hr', 'law');

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'finance'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'hr'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'law'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'finance'
WHERE u.name = 'finance';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'hr'
WHERE u.name = 'hr';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'law'
WHERE u.name = 'law';

INSERT OR IGNORE INTO documents(name) VALUES ('primerjalna_analiza_sistemov_organizacije.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('prihodki_od_udelezbe_na_dobicku_in_dividend.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('MKRR_Koncno-porocilo_27nov2025.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('financni-viri-slovenskih-obcin_e-izdaja.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('upravljanje_kapitalskih_virov_v_slovenskih_obcinah.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('SNSA_hr.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('Vrednotenje-spodbujanja-RR-programov-in-RR-projektov-Koncno-porocilo.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('Raziskovalno-porocilo-_-Javnomnenjska-raziskava-2017.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('Raziskovalno-porocilo-2022.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('gjiizdajasifrantinstruktura21.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('koncnoporocilo0redanalizaizmermikromre.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('OBVESTILO_POSAMEZNIKOM.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('fizikalnoozadjepodnebnihsprememb.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('analizastanjanapodrojuintelektualenlastninevsloveniji.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('sterleetal2024analizagnsskoncnoporocilo.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('elaboratuxportalipodatki.txt');

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'primerjalna_analiza_sistemov_organizacije.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'prihodki_od_udelezbe_na_dobicku_in_dividend.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'MKRR_Koncno-porocilo_27nov2025.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'financni-viri-slovenskih-obcin_e-izdaja.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'upravljanje_kapitalskih_virov_v_slovenskih_obcinah.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'hr'
WHERE d.name = 'SNSA_hr.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'hr'
WHERE d.name = 'Vrednotenje-spodbujanja-RR-programov-in-RR-projektov-Koncno-porocilo.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'hr'
WHERE d.name = 'Raziskovalno-porocilo-_-Javnomnenjska-raziskava-2017.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'hr'
WHERE d.name = 'Raziskovalno-porocilo-2022.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'gjiizdajasifrantinstruktura21.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'koncnoporocilo0redanalizaizmermikromre.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'OBVESTILO_POSAMEZNIKOM.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'fizikalnoozadjepodnebnihsprememb.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'analizastanjanapodrojuintelektualenlastninevsloveniji.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'sterleetal2024analizagnsskoncnoporocilo.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'law'
WHERE d.name = 'elaboratuxportalipodatki.txt';

COMMIT;
