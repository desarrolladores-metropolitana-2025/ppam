<?php
namespace Entities;

class TurnoEntity
{
    public int $id;
    public string $finiteState;   // estado actual del turno (FSM)
    public string $fecha;
    public string $hora_inicio;
    public string $hora_fin;
    public int $punto_id;

    public function __construct(array $row)
    {
        $this->id          = (int)$row['id'];
        $this->finiteState = trim($row['estado']) ?? 'pendiente'; // valor inicial
        $this->fecha       = $row['fecha'];
        $this->hora_inicio = $row['hora_inicio'];
        $this->hora_fin    = $row['hora_fin'];
        $this->punto_id    = (int)$row['punto_id'];
    }
}
