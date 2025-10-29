-- Sistema PPAM
-- Tablas generales
-- Modificación:  13/10/2025


CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
name VARCHAR(20) NOT NULL,
middle_name VARCHAR(20) DEFAULT NULL,
last_name       VARCHAR(20) NOT NULL,
 full_name VARCHAR(80) NOT NULL,
 password VARCHAR(255) NOT NULL,
 phone       VARCHAR(40) NOT NULL,
 email VARCHAR(160) UNIQUE,
 gender VARCHAR(12) DEFAULT NULL,
 role VARCHAR(50) DEFAULT 'publicador', -- puede usarse para permisos
 is_admin TINYINT(1) DEFAULT 0,  
 vehicle_available TINYINT(1) DEFAULT 0,
 languages JSON DEFAULT NULL, -- ["es","en"]
 idiomas_id,
 administrador TINYINT(1),
 vip TINYINT(1),
 capitan TINYINT(1),
 publicador TINYINT(1),
 bloqueado  TINYINT(1),
 experience VARCHAR(16),
 pioneering VARCHAR(20) DEFAULT NULL,
 priviledge   VARCHAR(20) DEFAULT NULL,
 participation DATE ,
 language VARCHAR(40) DEFAULT 'espanol', 
 congregacion_id INT,
 circuito_id INT,
 companion_id INT,
password_token VARCHAR(64) NULL,
token_expira DATETIME NULL,
 creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
-- Relacionar con congregación , circuito, compañero(user) (¿CASCADE?)
);

CREATE TABLE congregaciones (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  idioma  VARCHAR(60) DEFAULT NULL,
  circuito_id INT,
  cong_numero VARCHAR(10),
  tour_number   VARCHAR(10),
  direccion VARCHAR(100);
  ciudad  VARCHAR(20),
  codigo_postal VARCHAR(12)
);

CREATE TABLE circuitos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(60) NOT NULL,
  idioma VARCHAR(60) DEFAULT NULL,
  superintendente VARCHAR(40) DEFAULT NULL,
  direccion_super  VARCHAR(40) DEFAULT NULL
);

CREATE TABLE idiomas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(60) NOT NULL
);

CREATE TABLE puntos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(40) NOT NULL,
  lugar_encuentro VARCHAR(255),
  minimo_publicadores INT,
  maximo_publicadores INT,
  minimo_varones INT DEFAULT NULL,
  limites_primer_turno BIT DEFAULT NULL,
  limites_ultimo_turno BIT DEFAULT NULL,
  deposito_id INT,
  idiomas_id   INT,
  participantes_par BIT DEFAULT NULL,
  punto_completo BIT DEFAULT NULL,
  restriccion_asig BIT DEFAULT NULL,
   FOREIGN KEY (deposito_id) REFERENCES depositos(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
   FOREIGN KEY (idiomas_id) REFERENCES idiomas(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE,
);

CREATE TABLE IF NOT EXISTS punto_horarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  punto_id INT NOT NULL,
  dia_semana ENUM('lunes','martes','miércoles','jueves','viernes','sábado','domingo') NOT NULL,
  hora_desde TIME NOT NULL,
  hora_hasta TIME NOT NULL,
  FOREIGN KEY (punto_id) REFERENCES puntos(id) ON DELETE CASCADE
);

CREATE TABLE depositos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  direccion VARCHAR(255) DEFAULT NULL,
  ciudad VARCHAR(40) DEFAULT NULL,
  codigo_postal VARCHAR(12) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE disponibilidad (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  dia VARCHAR(20) NOT NULL,
  hora_inicio TIME NOT NULL,
  hora_fin TIME NOT NULL,
  frecuencia ENUM('semanal','mensual') DEFAULT 'semanal',
  cada INT DEFAULT 1,
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES users(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

CREATE TABLE ausencias (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  fecha_inicio DATE NOT NULL,
  fecha_fin DATE NOT NULL,
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES users(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE
);


CREATE TABLE IF NOT EXISTS experiencias (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  tipo VARCHAR(100) NOT NULL,
  fecha_experiencia DATE NOT NULL,
  hora TIME DEFAULT NULL,
  lugar VARCHAR(255),
  titulo VARCHAR(255) NOT NULL,
  descripcion TEXT,
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
);



CREATE TABLE turnos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  fecha DATE NOT NULL,
  hora TIME NOT NULL,
  tipo ENUM('fijo', 'eventual', 'suplencia'),
  estado ENUM('pendiente','asignado','completado') DEFAULT 'pendiente',
  FOREIGN KEY (usuario_id) REFERENCES users(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

CREATE TABLE solicitudes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  fecha DATE NOT NULL,
  estado ENUM('pendiente','aprobada','rechazada') DEFAULT 'pendiente',
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

-- Estructura de tabla sugerida: `news`
CREATE TABLE IF NOT EXISTS `news` (
  `id` INT  NOT NULL AUTO_INCREMENT,
  `user_id` INT  NOT NULL ,
  `title` VARCHAR(255) NOT NULL,
  `visible_from` DATETIME NULL DEFAULT NULL,
  `visible_until` DATETIME NULL DEFAULT NULL,
  `content_html` MEDIUMTEXT NULL,
  `visible_publisher` TINYINT(1) NOT NULL DEFAULT 1,
  `visible_captain`   TINYINT(1) NOT NULL DEFAULT 0,
  `visible_vip`       TINYINT(1) NOT NULL DEFAULT 0,
  `visible_admin`     TINYINT(1) NOT NULL DEFAULT 0,
  `attachment_path` VARCHAR(400) NULL,
  `read_count` INT UNSIGNED NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL,
  `updated_at` DATETIME NOT NULL,
  PRIMARY KEY (`id`),
  INDEX (`visible_from`),
  INDEX (`visible_until`),
  CONSTRAINT fk_news_usuario  FOREIGN KEY (user_id)  REFERENCES users(id) ON DELETE CASCADE   ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE news_reads (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  news_id INT UNSIGNED NOT NULL,
  user_id INT NULL,
  reader_key VARCHAR(128) NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX (news_id),
  INDEX (user_id),
  INDEX (reader_key),
  CONSTRAINT fk_news_reads_news FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ALTER TABLE news   ADD COLUMN user_id INT  NULL AFTER id;


ALTER TABLE news
  ADD 

