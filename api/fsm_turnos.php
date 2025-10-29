<?php
use Finite\State\State;
use Finite\StateMachine\StateMachine;
use Finite\Loader\ArrayLoader;

require_once __DIR__ . '/../fsm/vendor/autoload.php';

/**
 * Construye la máquina de estados para un turno.
 */
function buildTurnoStateMachine(array $turno)
{
    $sm = new StateMachine();

    $loader = new ArrayLoader([
        'class' => 'ArrayObject', // no usamos una clase fija
		'property_path' => 'finiteState', // <--- AGREGADO ESTA LÍNEA
        'states' => [
            'creado' => ['type' => State::TYPE_INITIAL],
            'abierto' => ['type' => State::TYPE_NORMAL],
            'planificado' => ['type' => State::TYPE_NORMAL],
            'publicado' => ['type' => State::TYPE_NORMAL],
            'cerrado' => ['type' => State::TYPE_FINAL],
            'cancelado' => ['type' => State::TYPE_FINAL],
        ],
        'transitions' => [
            'abrir' => ['from' => ['creado'], 'to' => 'abierto'],
            'planificar' => ['from' => ['abierto'], 'to' => 'planificado'],
            'publicar' => ['from' => ['planificado'], 'to' => 'publicado'],
            'cerrar' => ['from' => ['publicado'], 'to' => 'cerrado'],
            'cancelar' => ['from' => ['creado','abierto','planificado','publicado'], 'to' => 'cancelado'],
        ]
    ]);

    $loader->load($sm);
    // MODIFICACIÓN CLAVE: pasar 'finiteState' como segundo parámetro
    $sm->setObject(
        new ArrayObject(['finiteState' => $turno['estado'] ?? 'creado']),
        'finiteState' 
    );
    
    $sm->initialize();

    return $sm;
}
