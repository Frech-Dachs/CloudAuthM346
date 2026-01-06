-- MariaDB schema for CloudAuth admin panel
CREATE DATABASE IF NOT EXISTS cloudauth CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE cloudauth;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL UNIQUE,
  password_hash CHAR(64) NOT NULL,
  is_admin TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Track successful login events for auditing.
CREATE TABLE IF NOT EXISTS login_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) NOT NULL,
  logged_in_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_login_events_logged_in_at (logged_in_at)
);

-- The first registered user is promoted to admin by the application logic.
