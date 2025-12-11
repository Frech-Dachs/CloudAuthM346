CREATE DATABASE cloudauth
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE cloudauth;

CREATE TABLE users (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,   -- z.B. bcrypt/argon2 Hash
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    is_admin TINYINT(1) NOT NULL DEFAULT 0
) ENGINE=InnoDB

CREATE TABLE login_events (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    login_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip_address VARCHAR(45),          -- IPv4/IPv6
    success TINYINT(1) NOT NULL,     -- 1 = Erfolg, 0 = Fehlgeschlagen
    CONSTRAINT fk_login_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

