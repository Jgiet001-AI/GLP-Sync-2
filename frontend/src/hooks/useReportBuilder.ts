import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, useCallback } from 'react'
import toast from 'react-hot-toast'
import { customReportsApi } from '../api/custom_reports'
import type {
  FieldConfig,
  FilterConfig,
  GroupingConfig,
  SortingConfig,
  ReportConfig,
  CreateReportRequest,
  UpdateReportRequest,
  CustomReportResponse,
  ExecuteReportResponse,
  FieldsResponse,
  AggregationFunction,
  FilterOperator,
  LogicOperator,
  SortDirection,
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

export function useReportBuilder() {
  const queryClient = useQueryClient()

  // Report builder state
  const [fields, setFields] = useState<FieldConfig[]>([])
  const [filters, setFilters] = useState<FilterConfig[]>([])
  const [grouping, setGrouping] = useState<GroupingConfig[]>([])
  const [sorting, setSorting] = useState<SortingConfig[]>([])
  const [limit, setLimit] = useState<number | null>(null)
  const [currentReport, setCurrentReport] = useState<CustomReportResponse | null>(null)
  const [previewData, setPreviewData] = useState<ExecuteReportResponse | null>(null)

  // Available fields query
  const fieldsQuery = useQuery({
    queryKey: ['report-fields'],
    queryFn: () => customReportsApi.getAvailableFields(),
    staleTime: 1000 * 60 * 10, // 10 minutes
  })

  // Saved reports list query
  const reportsQuery = useQuery({
    queryKey: ['custom-reports'],
    queryFn: () => customReportsApi.listReports(),
    staleTime: 1000 * 60 * 5, // 5 minutes
  })

  // Create report mutation
  const createMutation = useMutation({
    mutationFn: (request: CreateReportRequest) => customReportsApi.createReport(request),
    onSuccess: (data: CustomReportResponse) => {
      setCurrentReport(data)
      toast.success(`Report "${data.name}" created successfully`)
      queryClient.invalidateQueries({ queryKey: ['custom-reports'] })
    },
    onError: (error: unknown) => {
      toast.error(`Create failed: ${formatError(error)}`)
    },
  })

  // Update report mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, request }: { id: string; request: UpdateReportRequest }) =>
      customReportsApi.updateReport(id, request),
    onSuccess: (data: CustomReportResponse) => {
      setCurrentReport(data)
      toast.success(`Report "${data.name}" updated successfully`)
      queryClient.invalidateQueries({ queryKey: ['custom-reports'] })
    },
    onError: (error: unknown) => {
      toast.error(`Update failed: ${formatError(error)}`)
    },
  })

  // Delete report mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => customReportsApi.deleteReport(id),
    onSuccess: () => {
      toast.success('Report deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['custom-reports'] })
      if (currentReport) {
        setCurrentReport(null)
        resetConfig()
      }
    },
    onError: (error: unknown) => {
      toast.error(`Delete failed: ${formatError(error)}`)
    },
  })

  // Execute report mutation
  const executeMutation = useMutation({
    mutationFn: (params: { id?: string; config?: ReportConfig; page?: number; pageSize?: number }) => {
      if (params.id) {
        return customReportsApi.executeReport(params.id, {
          format: 'json',
          page: params.page || 1,
          page_size: params.pageSize || 100,
        })
      }
      // For unsaved reports, we would need a different endpoint or approach
      // For now, require saving the report first
      throw new Error('Cannot execute unsaved report. Please save first.')
    },
    onSuccess: (data: ExecuteReportResponse) => {
      setPreviewData(data)
      if (data.success) {
        toast.success(`Report executed in ${data.execution_time_ms}ms`)
      } else {
        toast.error(`Execution failed: ${data.errors.join(', ')}`)
      }
    },
    onError: (error: unknown) => {
      toast.error(`Execute failed: ${formatError(error)}`)
    },
  })

  // Field actions
  const addField = useCallback(
    (table: string, field: string, alias?: string | null, aggregation?: AggregationFunction | null) => {
      const newField: FieldConfig = {
        table,
        field,
        alias: alias || null,
        aggregation: aggregation || null,
      }
      setFields((prev) => [...prev, newField])
    },
    []
  )

  const removeField = useCallback((index: number) => {
    setFields((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const updateField = useCallback(
    (index: number, updates: Partial<FieldConfig>) => {
      setFields((prev) =>
        prev.map((field, i) => (i === index ? { ...field, ...updates } : field))
      )
    },
    []
  )

  // Filter actions
  const addFilter = useCallback(
    (
      field: string,
      operator: FilterOperator,
      value: any,
      table?: string | null,
      logic?: LogicOperator
    ) => {
      const newFilter: FilterConfig = {
        field,
        table: table || null,
        operator,
        value,
        logic: logic || 'AND',
      }
      setFilters((prev) => [...prev, newFilter])
    },
    []
  )

  const removeFilter = useCallback((index: number) => {
    setFilters((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const updateFilter = useCallback(
    (index: number, updates: Partial<FilterConfig>) => {
      setFilters((prev) =>
        prev.map((filter, i) => (i === index ? { ...filter, ...updates } : filter))
      )
    },
    []
  )

  // Grouping actions
  const addGrouping = useCallback((field: string, table?: string | null) => {
    const newGroup: GroupingConfig = {
      field,
      table: table || null,
    }
    setGrouping((prev) => [...prev, newGroup])
  }, [])

  const removeGrouping = useCallback((index: number) => {
    setGrouping((prev) => prev.filter((_, i) => i !== index))
  }, [])

  // Sorting actions
  const addSorting = useCallback(
    (field: string, direction: SortDirection, table?: string | null) => {
      const newSort: SortingConfig = {
        field,
        table: table || null,
        direction,
      }
      setSorting((prev) => [...prev, newSort])
    },
    []
  )

  const removeSorting = useCallback((index: number) => {
    setSorting((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const updateSorting = useCallback(
    (index: number, updates: Partial<SortingConfig>) => {
      setSorting((prev) =>
        prev.map((sort, i) => (i === index ? { ...sort, ...updates } : sort))
      )
    },
    []
  )

  // Config management
  const resetConfig = useCallback(() => {
    setFields([])
    setFilters([])
    setGrouping([])
    setSorting([])
    setLimit(null)
    setPreviewData(null)
  }, [])

  const getConfig = useCallback((): ReportConfig => {
    return {
      fields,
      filters,
      grouping,
      sorting,
      limit,
    }
  }, [fields, filters, grouping, sorting, limit])

  const loadConfig = useCallback((config: ReportConfig) => {
    setFields(config.fields)
    setFilters(config.filters)
    setGrouping(config.grouping)
    setSorting(config.sorting)
    setLimit(config.limit)
    setPreviewData(null)
  }, [])

  // Report management
  const loadReport = useCallback((report: CustomReportResponse) => {
    setCurrentReport(report)
    loadConfig(report.config)
  }, [loadConfig])

  const saveReport = useCallback(
    (name: string, description?: string | null, isShared = false, sharedWith: string[] = []) => {
      const config = getConfig()

      if (currentReport) {
        // Update existing report
        updateMutation.mutate({
          id: currentReport.id,
          request: {
            name,
            description,
            config,
            is_shared: isShared,
            shared_with: sharedWith,
          },
        })
      } else {
        // Create new report
        createMutation.mutate({
          name,
          description,
          config,
          is_shared: isShared,
          shared_with: sharedWith,
        })
      }
    },
    [currentReport, getConfig, createMutation, updateMutation]
  )

  const deleteReport = useCallback(
    (id: string) => {
      deleteMutation.mutate(id)
    },
    [deleteMutation]
  )

  const executeReport = useCallback(
    (page = 1, pageSize = 100) => {
      if (currentReport) {
        executeMutation.mutate({
          id: currentReport.id,
          page,
          pageSize,
        })
      } else {
        toast.error('Please save the report before executing')
      }
    },
    [currentReport, executeMutation]
  )

  const downloadReport = useCallback(
    async (format: 'csv' | 'xlsx', filename?: string) => {
      if (!currentReport) {
        toast.error('Please save the report before downloading')
        return
      }

      try {
        await customReportsApi.downloadReport(currentReport.id, format, filename)
        toast.success(`Report downloaded as ${format.toUpperCase()}`)
      } catch (error) {
        toast.error(`Download failed: ${formatError(error)}`)
      }
    },
    [currentReport]
  )

  return {
    // State
    fields,
    filters,
    grouping,
    sorting,
    limit,
    currentReport,
    previewData,

    // Queries
    availableFields: fieldsQuery.data,
    isLoadingFields: fieldsQuery.isLoading,
    savedReports: reportsQuery.data,
    isLoadingReports: reportsQuery.isLoading,

    // Field actions
    addField,
    removeField,
    updateField,

    // Filter actions
    addFilter,
    removeFilter,
    updateFilter,

    // Grouping actions
    addGrouping,
    removeGrouping,

    // Sorting actions
    addSorting,
    removeSorting,
    updateSorting,

    // Limit action
    setLimit,

    // Config management
    resetConfig,
    getConfig,
    loadConfig,

    // Report management
    loadReport,
    saveReport,
    deleteReport,
    executeReport,
    downloadReport,

    // Mutation states
    isSaving: createMutation.isPending || updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
    isExecuting: executeMutation.isPending,
  }
}
