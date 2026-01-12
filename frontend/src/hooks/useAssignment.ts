import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, useCallback } from 'react'
import toast from 'react-hot-toast'
import { assignmentApi } from '../api/client'
import type {
  ApplyRequest,
  ApplyResponse,
  DeviceAssignment,
  ProcessResponse,
  ReportResponse,
  WorkflowStep,
} from '../types'
import { ApiError } from '../types'

// Helper to format error messages from ApiError
function formatError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isValidationError && error.errors?.length) {
      return `Validation failed: ${error.errors.length} error(s)`
    }
    if (error.isAuthError) {
      return 'Authentication required. Please refresh and try again.'
    }
    if (error.isServerError) {
      return `Server error (${error.status}): ${error.detail}`
    }
    return `${error.status ? `Error ${error.status}: ` : ''}${error.detail}`
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'An unknown error occurred'
}

export function useAssignment() {
  const queryClient = useQueryClient()

  // Workflow state
  const [step, setStep] = useState<WorkflowStep>('upload')
  const [devices, setDevices] = useState<DeviceAssignment[]>([])
  const [selectedSerials, setSelectedSerials] = useState<Set<string>>(new Set())
  const [applyResult, setApplyResult] = useState<ApplyResponse | null>(null)
  const [report, setReport] = useState<ReportResponse | null>(null)

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: (file: File) => assignmentApi.uploadExcel(file),
    onSuccess: (data: ProcessResponse) => {
      if (data.success) {
        setDevices(data.devices)
        setSelectedSerials(new Set(data.devices.map((d) => d.serial_number)))
        setStep('review')
        toast.success(`Processed ${data.total_rows} devices`)
      } else {
        toast.error(`Validation failed: ${data.errors.length} errors`)
      }
    },
    onError: (error: unknown) => {
      toast.error(`Upload failed: ${formatError(error)}`)
    },
  })

  // Options query
  const optionsQuery = useQuery({
    queryKey: ['options'],
    queryFn: () => assignmentApi.getOptions(),
    enabled: step === 'assign' || step === 'review',
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  // Apply mutation
  const applyMutation = useMutation({
    mutationFn: (request: ApplyRequest) => assignmentApi.applyAssignments(request),
    onSuccess: (data: ApplyResponse) => {
      setApplyResult(data)
      setStep('report')
      if (data.success) {
        toast.success('Assignments applied successfully')
      } else {
        toast.error(`Some operations failed: ${data.errors} errors`)
      }
    },
    onError: (error: unknown) => {
      toast.error(`Apply failed: ${formatError(error)}`)
    },
  })

  // Sync mutation
  const syncMutation = useMutation({
    mutationFn: () => assignmentApi.syncAndReport(),
    onSuccess: (data: ReportResponse) => {
      setReport(data)
      toast.success('Sync completed')
      queryClient.invalidateQueries({ queryKey: ['options'] })
    },
    onError: (error: unknown) => {
      toast.error(`Sync failed: ${formatError(error)}`)
    },
  })

  // Actions
  const uploadFile = useCallback((file: File) => {
    uploadMutation.mutate(file)
  }, [uploadMutation])

  const toggleDevice = useCallback((serial: string) => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      if (next.has(serial)) {
        next.delete(serial)
      } else {
        next.add(serial)
      }
      return next
    })
  }, [])

  const selectAll = useCallback(() => {
    setSelectedSerials(new Set(devices.map((d) => d.serial_number)))
  }, [devices])

  const deselectAll = useCallback(() => {
    setSelectedSerials(new Set())
  }, [])

  const deselectComplete = useCallback(() => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (d.status === 'fully_assigned') {
          next.delete(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const selectComplete = useCallback(() => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (d.status === 'fully_assigned') {
          next.add(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const selectByType = useCallback((deviceType: string) => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (d.device_type === deviceType) {
          next.add(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const deselectByType = useCallback((deviceType: string) => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (d.device_type === deviceType) {
          next.delete(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const selectByModel = useCallback((model: string) => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (d.model === model) {
          next.add(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const deselectByModel = useCallback((model: string) => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (d.model === model) {
          next.delete(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const selectNotInDb = useCallback(() => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (!d.device_id) {
          next.add(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const deselectNotInDb = useCallback(() => {
    setSelectedSerials((prev) => {
      const next = new Set(prev)
      devices.forEach((d) => {
        if (!d.device_id) {
          next.delete(d.serial_number)
        }
      })
      return next
    })
  }, [devices])

  const updateDevice = useCallback(
    (serial: string, updates: Partial<DeviceAssignment>) => {
      setDevices((prev) =>
        prev.map((d) =>
          d.serial_number === serial ? { ...d, ...updates } : d
        )
      )
    },
    []
  )

  const applyToSelected = useCallback(
    (updates: Partial<DeviceAssignment>) => {
      setDevices((prev) =>
        prev.map((d) =>
          selectedSerials.has(d.serial_number) ? { ...d, ...updates } : d
        )
      )
    },
    [selectedSerials]
  )

  const applyAssignments = useCallback((overrideDevices?: DeviceAssignment[]) => {
    const devicesToUse = overrideDevices ?? devices
    const selectedDevices = devicesToUse.filter((d) =>
      selectedSerials.has(d.serial_number)
    )

    const request: ApplyRequest = {
      devices: selectedDevices.map((d) => ({
        serial_number: d.serial_number,
        device_id: d.device_id,
        device_type: d.device_type,
        mac_address: d.mac_address,
        // Current assignments from database - needed for gap detection
        current_subscription_id: d.current_subscription_id,
        current_application_id: d.current_application_id,
        current_tags: d.current_tags || {},
        // User selections
        selected_subscription_id: d.selected_subscription_id,
        selected_application_id: d.selected_application_id,
        selected_region: d.selected_region,  // Region code - required with application_id
        selected_tags: d.selected_tags || {},
      })),
      wait_for_completion: true,
    }

    applyMutation.mutate(request)
  }, [devices, selectedSerials, applyMutation])

  const syncWithGreenLake = useCallback(() => {
    syncMutation.mutate()
  }, [syncMutation])

  const reset = useCallback(() => {
    setStep('upload')
    setDevices([])
    setSelectedSerials(new Set())
    setApplyResult(null)
    setReport(null)
  }, [])

  const goToStep = useCallback((newStep: WorkflowStep) => {
    setStep(newStep)
  }, [])

  return {
    // State
    step,
    devices,
    selectedSerials,
    options: optionsQuery.data ?? null,
    applyResult,
    report,

    // Loading states
    isUploading: uploadMutation.isPending,
    isLoadingOptions: optionsQuery.isLoading,
    isApplying: applyMutation.isPending,
    isSyncing: syncMutation.isPending,

    // Actions
    uploadFile,
    toggleDevice,
    selectAll,
    deselectAll,
    deselectComplete,
    selectComplete,
    selectByType,
    deselectByType,
    selectByModel,
    deselectByModel,
    selectNotInDb,
    deselectNotInDb,
    updateDevice,
    applyToSelected,
    applyAssignments,
    syncWithGreenLake,
    reset,
    goToStep,
    setDevices,

    // Derived state
    selectedCount: selectedSerials.size,
    totalCount: devices.length,
  }
}
