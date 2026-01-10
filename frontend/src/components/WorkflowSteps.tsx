import { memo } from 'react'
import { Check } from 'lucide-react'
import clsx from 'clsx'
import type { WorkflowStep } from '../types'

interface WorkflowStepsProps {
  currentStep: WorkflowStep
  onStepClick?: (step: WorkflowStep) => void
}

const steps: { id: WorkflowStep; label: string }[] = [
  { id: 'upload', label: 'Upload' },
  { id: 'review', label: 'Review' },
  { id: 'assign', label: 'Assign' },
  { id: 'apply', label: 'Apply' },
  { id: 'report', label: 'Report' },
]

export const WorkflowSteps = memo(function WorkflowSteps({ currentStep, onStepClick }: WorkflowStepsProps) {
  const currentIndex = steps.findIndex((s) => s.id === currentStep)

  return (
    <nav className="flex items-center justify-center mb-8" aria-label="Workflow progress" data-testid="workflow-steps">
      <ol className="flex items-center space-x-4" role="list">
        {steps.map((step, index) => {
          const isComplete = index < currentIndex
          const isCurrent = step.id === currentStep
          const isClickable = onStepClick && index <= currentIndex

          return (
            <li key={step.id} className="flex items-center">
              {index > 0 && (
                <div
                  className={clsx(
                    'w-12 h-0.5 mr-4 transition-colors',
                    index <= currentIndex ? 'bg-hpe-green' : 'bg-slate-600'
                  )}
                  aria-hidden="true"
                />
              )}

              <button
                onClick={() => isClickable && onStepClick(step.id)}
                disabled={!isClickable}
                className={clsx(
                  'flex items-center',
                  isClickable && 'cursor-pointer',
                  !isClickable && 'cursor-default'
                )}
                aria-current={isCurrent ? 'step' : undefined}
                data-testid={`workflow-step-${step.id}`}
              >
                <span
                  className={clsx(
                    'flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors',
                    isComplete && 'bg-hpe-green border-hpe-green text-white',
                    isCurrent && 'border-hpe-green text-hpe-green bg-slate-900',
                    !isComplete && !isCurrent && 'border-slate-600 text-slate-500 bg-slate-900'
                  )}
                >
                  {isComplete ? (
                    <Check className="w-5 h-5" aria-hidden="true" />
                  ) : (
                    <span className="text-sm font-medium">{index + 1}</span>
                  )}
                </span>

                <span
                  className={clsx(
                    'ml-2 text-sm font-medium',
                    isCurrent && 'text-hpe-green',
                    isComplete && 'text-slate-300',
                    !isComplete && !isCurrent && 'text-slate-500'
                  )}
                >
                  {step.label}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
})
