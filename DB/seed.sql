BEGIN TRANSACTION;

INSERT OR IGNORE INTO groups(name) VALUES ('finance');
INSERT OR IGNORE INTO groups(name) VALUES ('HR');
INSERT OR IGNORE INTO groups(name) VALUES ('CEO');

INSERT OR IGNORE INTO users(name, password_hash) VALUES ('šef', '__PASSWORD_HASH__');
INSERT OR IGNORE INTO users(name, password_hash) VALUES ('finance', '__PASSWORD_HASH__');
INSERT OR IGNORE INTO users(name, password_hash) VALUES ('HR', '__PASSWORD_HASH__');

UPDATE users
SET password_hash = '__PASSWORD_HASH__'
WHERE name IN ('šef', 'finance', 'HR');

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'finance'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'HR'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'finance'
WHERE u.name = 'finance';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'HR'
WHERE u.name = 'HR';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'HR'
WHERE u.name = 'HR';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'CEO'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO user_group(user_id, group_id)
SELECT u.id, g.id
FROM users u
JOIN groups g ON g.name = 'CEO'
WHERE u.name = 'šef';

INSERT OR IGNORE INTO documents(name) VALUES ('doc1.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('doc2.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('doc3.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('doc4.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('doc5.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('doc6.txt');
INSERT OR IGNORE INTO documents(name) VALUES ('stroski_2023.csv');

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'doc1.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'HR'
WHERE d.name = 'doc2.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'doc3.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'CEO'
WHERE d.name = 'doc4.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'doc5.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'CEO'
WHERE d.name = 'doc6.txt';

INSERT OR IGNORE INTO document_group(document_id, group_id)
SELECT d.id, g.id
FROM documents d
JOIN groups g ON g.name = 'finance'
WHERE d.name = 'stroski_2023.csv';

COMMIT;
