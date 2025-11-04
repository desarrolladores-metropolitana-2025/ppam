-- Disponibilidad → usuario declara disponibilidad.
-- 
-- Solicitudes → usuario pide turno (rol = capitán/publicador).
-- 
-- Turnos → admin crea turnos (ej: todos los días 9–11).
-- 
-- Turno_participantes → se confirman asignaciones (desde solicitudes o manual).
-- 
-- Ausencias → si un usuario confirmado no va, se marca aquí.___
--
--  Sistema Metropoliplan / PPAM
--  Modificado:    13/10/25

-- Idiomas
CREATE TABLE IF NOT EXISTS idiomas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(80) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Depósitos (almacenamiento de carritos / exhibidores)
CREATE TABLE IF NOT EXISTS depositos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(120) NOT NULL,
  direccion VARCHAR(255) DEFAULT NULL,
  ciudad VARCHAR(80) DEFAULT NULL,
  codigo_postal VARCHAR(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Puntos de predicación
CREATE TABLE IF NOT EXISTS puntos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(150) NOT NULL,
  lugar_encuentro VARCHAR(255) DEFAULT NULL,
  minimo_publicadores INT DEFAULT 0,
  maximo_publicadores INT DEFAULT 3,
  minimo_varones INT DEFAULT NULL,
  limites_primer_turno TINYINT(1) DEFAULT 0,
  limites_ultimo_turno TINYINT(1) DEFAULT 0,
  deposito_id INT DEFAULT NULL,
  idiomas_id INT DEFAULT NULL,
  participantes_par TINYINT(1) DEFAULT 0,
  punto_completo TINYINT(1) DEFAULT 0,
  restriccion_asig TINYINT(1) DEFAULT 0,
  metadata JSON DEFAULT NULL, -- para datos libres (tags, accesos, etc)
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (deposito_id) REFERENCES depositos(id) ON DELETE SET NULL ON UPDATE CASCADE,
  FOREIGN KEY (idiomas_id) REFERENCES idiomas(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS punto_horarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  punto_id INT NOT NULL,
  dia_semana ENUM('lunes','martes','miércoles','jueves','viernes','sábado','domingo') NOT NULL,
  hora_desde TIME NOT NULL,
  hora_hasta TIME NOT NULL,
  FOREIGN KEY (punto_id) REFERENCES puntos(id) ON DELETE CASCADE
);

-- Disponibilidad semanal de cada punto: Horarios "oficiales" por punto (útil para generar plantillas de turnos)
CREATE TABLE IF NOT EXISTS punto_horarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  punto_id INT NOT NULL,
  dia_semana TINYINT NOT NULL, -- 1..7
  hora_inicio TIME NOT NULL,
  hora_fin TIME NOT NULL,
  activo TINYINT(1) DEFAULT 1,
  FOREIGN KEY (punto_id) REFERENCES puntos(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;



-- USE u962788881_Metropoliplan;


-- Disponibilidades explícitas del usuario
CREATE TABLE IF NOT EXISTS disponibilidades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  dia_semana TINYINT NOT NULL, -- 1..7
  hora_inicio TIME NOT NULL,
  hora_fin TIME NOT NULL,
  frecuencia ENUM('semanal','mensual','una-vez') DEFAULT 'semanal',
  cada INT DEFAULT 1,
  start_date DATE DEFAULT NULL, -- desde cuando aplica (opcional)
  end_date DATE DEFAULT NULL,
  rrule VARCHAR(255) DEFAULT NULL, -- opcional (iCal RRULE) para necesidades avanzadas
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

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

-- Tabla principal de turnos programados
CREATE TABLE IF NOT EXISTS turnos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  fecha DATE NOT NULL,
  hora_inicio TIME NOT NULL,
  hora_fin TIME NOT NULL,
  punto_id INT NOT NULL,
  tipo ENUM('fijo','eventual','suplencia','condicional') NOT NULL DEFAULT 'eventual',
  estado ENUM('creado','abierto','asignaciones_modificadas','planificado','publicado','completado','cancelado') NOT NULL DEFAULT 'creado',
  minimo_publicadores INT DEFAULT NULL,
  maximo_publicadores INT DEFAULT NULL,
  captain_required TINYINT(1) DEFAULT 1,
  published_at TIMESTAMP NULL DEFAULT NULL,
  validated_at TIMESTAMP NULL DEFAULT NULL,
  created_by INT DEFAULT NULL, -- admin que creó
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  metadata JSON DEFAULT NULL, -- para flags, tags, ratio, etc
  UNIQUE KEY uk_turno_punto_fecha_hora (punto_id, fecha, hora_inicio),
  FOREIGN KEY (punto_id) REFERENCES puntos(id) ON DELETE CASCADE ON UPDATE CASCADE,
  FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Participantes efectivamente asignados a un turno
CREATE TABLE IF NOT EXISTS turno_participantes (
  turno_id INT NOT NULL,
  usuario_id INT NOT NULL,
  rol ENUM('capitan','publicador') NOT NULL DEFAULT 'publicador',
  asignado_por INT DEFAULT NULL,
  asignado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  asistio TINYINT(1) DEFAULT 0,
  es_reemplazo TINYINT(1) DEFAULT 0,
  PRIMARY KEY (turno_id, usuario_id),
  FOREIGN KEY (turno_id) REFERENCES turnos(id) ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (asignado_por) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Participantes confirmados en un turno
CREATE TABLE IF NOT EXISTS turno_participantes (
  turno_id INT NOT NULL,
  usuario_id INT NOT NULL,
  rol ENUM('capitan','publicador') NOT NULL,
  asistio TINYINT(1) DEFAULT 0,
  PRIMARY KEY (turno_id, usuario_id),
  FOREIGN KEY (turno_id) REFERENCES turnos(id) 
    ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES users(id) 
    ON DELETE CASCADE
);

-- Informes por turno (lo que se envía / guarda)
CREATE TABLE IF NOT EXISTS informes_turno (
  id INT AUTO_INCREMENT PRIMARY KEY,
  turno_id INT NOT NULL,
  estado_informe ENUM('borrador','entregado','cerrado') DEFAULT 'borrador',
  participants_json JSON DEFAULT NULL, -- lista de participantes como JSON
  metrics_json JSON DEFAULT NULL, -- p.ej. { "horas":2, "biblias":0, ... }
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (turno_id) REFERENCES turnos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Solicitudes de usuarios a un turno (requests)
CREATE TABLE IF NOT EXISTS solicitudes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  turno_id INT NOT NULL,
  rol ENUM('capitan','publicador') DEFAULT 'publicador',
  estado ENUM('pendiente','aprobada','rechazada','cancelada') DEFAULT 'pendiente',
  motivo VARCHAR(255) DEFAULT NULL,
  fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  processed_by INT DEFAULT NULL,
  processed_at TIMESTAMP NULL DEFAULT NULL,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (turno_id) REFERENCES turnos(id) ON DELETE CASCADE,
  FOREIGN KEY (processed_by) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- Ausencias
CREATE TABLE IF NOT EXISTS ausencias (
  id INT AUTO_INCREMENT PRIMARY KEY,
  usuario_id INT NOT NULL,
  turno_id INT NOT NULL,
  motivo VARCHAR(255),
  fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_fin TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_aviso TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (usuario_id) REFERENCES users(id)
    ON DELETE CASCADE 
    ON UPDATE CASCADE,
  FOREIGN KEY (turno_id) REFERENCES turnos(id)
    ON DELETE CASCADE
    ON UPDATE CASCADE
);

-- Notificaciones para usuarios (mail/push/SMS) generadas por el sistema/bot
CREATE TABLE IF NOT EXISTS  notificaciones (
  id INT AUTO_INCREMENT PRIMARY KEY,
   turno_id INT NOT NULL,
  usuario_id INT NOT NULL,
  tipo ENUM('vacante','cubierto','recordatorio','cancelado') NOT NULL,
  mensaje TEXT NOT NULL,
  payload JSON DEFAULT NULL, -- contenido estructurado (link, texto, datos)
  canal ENUM('email','push','sms') DEFAULT 'email',
  estado ENUM('pending','sent','failed') DEFAULT 'pending',
  intentos INT DEFAULT 0,
  enviado TINYINT(1) DEFAULT 0,
  creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  sent_at TIMESTAMP NULL DEFAULT NULL,
  FOREIGN KEY (turno_id) REFERENCES turnos(id) ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE turnos_log (
  id INT AUTO_INCREMENT PRIMARY KEY,
  turno_id INT NOT NULL,
  estado_anterior VARCHAR(20),
  estado_nuevo VARCHAR(20),
  cambiado_por INT,
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (turno_id) REFERENCES turnos(id)
);

-- ALTER TABLE turnos 
--  MODIFY COLUMN estado ENUM(
--    'pendiente',   -- creado pero sin abrir solicitudes
--    'abierto',     -- abierto a solicitudes
--    'planificado', -- admin asignó participantes
--    'publicado',   -- asignaciones visibles
--    'completado',  -- ya ocurrió
--    'cancelado'    -- anulado
--  ) DEFAULT 'pendiente';

-- Preferencias usuario <-> punto (preferido / posible / no_posible)
CREATE TABLE IF NOT EXISTS user_point_preferences (
  usuario_id INT NOT NULL,
  punto_id INT NOT NULL,
  nivel ENUM('preferido','posible','no_posible') NOT NULL DEFAULT 'posible',
  prioridad INT DEFAULT 0,
  PRIMARY KEY (usuario_id, punto_id),
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (punto_id) REFERENCES puntos(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;



-- Preferencias de puntos configuradas por el usuario
CREATE TABLE preferencias_puntos (
  usuario_id INT NOT NULL,
  punto_id INT NOT NULL,
  preferencia ENUM('preferido','posible','no_posible') NOT NULL,
  prioridad INT DEFAULT 0,
  PRIMARY KEY (usuario_id, punto_id),
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (punto_id) REFERENCES puntos(id) ON DELETE CASCADE
);


CREATE TABLE reemplazos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  turno_id INT NOT NULL,
  usuario_id INT NOT NULL, -- el que cancela
  rol ENUM('capitan','publicador') NOT NULL,
  estado ENUM('abierto','cubierto','expirado') DEFAULT 'abierto',
  fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_cierre TIMESTAMP NULL,
  FOREIGN KEY (turno_id) REFERENCES turnos(id) ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE reemplazo_candidatos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  reemplazo_id INT NOT NULL,
  usuario_id INT NOT NULL, -- candidato que fue notificado
  aceptado TINYINT(1) DEFAULT 0,
  fecha_notificacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  fecha_respuesta TIMESTAMP NULL,
  FOREIGN KEY (reemplazo_id) REFERENCES reemplazos(id) ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE
);


ALTER TABLE turno_participantes ADD COLUMN reemplazo_pendiente TINYINT(1) DEFAULT 0;
CREATE TABLE pedidos_reemplazo (
  id INT AUTO_INCREMENT PRIMARY KEY,
  turno_id INT NOT NULL,
  usuario_id INT NOT NULL,
  motivo VARCHAR(255),
  estado ENUM('pendiente','aceptado','rechazado') DEFAULT 'pendiente',
  fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (turno_id) REFERENCES turnos(id) ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES users(id) ON DELETE CASCADE
);


-- DELIMITER $$

-- CREATE TRIGGER validar_estado_turno
-- BEFORE UPDATE ON turnos
-- FOR EACH

