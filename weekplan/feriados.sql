-- Feriados (para reconocer días que afectan la planificación/bot)
CREATE TABLE IF NOT EXISTS feriados (
  id INT AUTO_INCREMENT PRIMARY KEY,
  fecha DATE NOT NULL,
  nombre VARCHAR(200) DEFAULT NULL,
  recurrente TINYINT(1) DEFAULT 0, -- 1 si se repite anualmente (ej. 25-12)
  region VARCHAR(100) DEFAULT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (fecha, region)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;