$transiciones = [
  'creado' => [
    'abrir_solicitudes' => 'abierto',
    'cancelar' => 'cancelado'
  ],
  'abierto' => [
    'cerrar_solicitudes' => 'modificado',
    'cancelar' => 'cancelado'
  ],
  'modificado' => [
    'planificar' => 'planificado',
    'cancelar' => 'cancelado'
  ],
  'planificado' => [
    'publicar' => 'publicado',
    'cancelar' => 'cancelado'
  ],
  'publicado' => [
    'editar' => 'modificado',
    'cancelar' => 'cancelado'
  ]
];
