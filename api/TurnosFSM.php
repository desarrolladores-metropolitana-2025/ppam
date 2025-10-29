<?php
namespace FSM;

use Entities\TurnoEntity;
use Finite\StateMachine\StateMachine;
use Finite\State\State;
use Finite\Transition\Transition;
use Finite\State\Accessor\PropertyPathStateAccessor;

class TurnosFSM
{
    private StateMachine $sm;

    public function __construct(TurnoEntity $turno)
    {
        // 👇 OJO: acá solo el objeto
        $this->sm = new StateMachine($turno);

        // 👇 Y acá le decimos cómo leer el estado
        $this->sm->setStateAccessor(new PropertyPathStateAccessor('finiteState'));

        $this->configure();
        $this->sm->initialize();
    }

    private function configure(): void
    {
		/*
creado
pendiente
abierto
asignado
planificado
publicado
completado
cancelado
DB:  enum('creado','pendiente','abierto','asignado','planificado','publicado','completado','cancelado')
		*/
		
        $this->sm->addState(new State('creado', State::TYPE_INITIAL));
        $this->sm->addState(new State('pendiente'));
		$this->sm->addState(new State('abierto'));
		$this->sm->addState(new State('asignado'));
        $this->sm->addState(new State('planificado'));
        $this->sm->addState(new State('publicado'));
        $this->sm->addState(new State('completado'));
        $this->sm->addState(new State('cancelado', State::TYPE_FINAL));

        $this->sm->addTransition(new Transition('asignar', 'pendiente', 'asignado'));
        $this->sm->addTransition(new Transition('planificar', 'abierto', 'planificado'));
        $this->sm->addTransition(new Transition('publicar', 'planificado', 'publicado'));
        $this->sm->addTransition(new Transition('completar', 'publicado', 'completado'));
        $this->sm->addTransition(new Transition('cancelar', ['pendiente'],  'cancelado'));
    }

    public function can(string $transition): bool
    {
        return $this->sm->can($transition);
    }

    public function apply(string $transition): void
    {
        $this->sm->apply($transition);
    }

    public function getState(): string
    {
        return $this->sm->getCurrentState()->getName();
    }
}
