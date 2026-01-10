import { useState, useMemo, useCallback, useEffect } from 'react'
import type { DeviceAssignment, OptionsResponse, Subscription, TypeAssignmentConfig } from '../types'

// Map device types to subscription categories for filtering
const TYPE_TO_SUBSCRIPTION_CATEGORY: Record<string, string> = {
  'IAP': 'CENTRAL_AP',
  'AP': 'CENTRAL_AP',
  'Switch': 'CENTRAL_SWITCH',
  'Gateway': 'CENTRAL_GW',
  'SWITCH': 'CENTRAL_SWITCH',
  'GATEWAY': 'CENTRAL_GW',
}

// Device types that need model-specific subscription filtering
const MODEL_FILTERED_TYPES = ['SWITCH', 'Switch', 'GATEWAY', 'Gateway']

// Extract model series from device model (e.g., "6200F" -> "6200", "6300M" -> "6300")
function extractModelSeries(model: string | null | undefined): string | null {
  if (!model) return null
  // Extract numeric part (e.g., "6200F" -> "6200", "6300" -> "6300")
  const match = model.match(/^(\d+)/)
  return match ? match[1] : null
}

// Check if subscription tier matches device model
function tierMatchesModel(tier: string | null | undefined, modelSeries: string | null): boolean {
  if (!tier || !modelSeries) return false
  // Tier format: "FOUNDATION_SWITCH_6200" or "FOUNDATION_GW_9004"
  return tier.includes(modelSeries)
}

interface DeviceTypeGroup {
  deviceType: string
  model: string | null  // For model-specific grouping
  groupKey: string      // Unique key for this group
  displayName: string
  devices: DeviceAssignment[]
  compatibleSubscriptions: Subscription[]
}

interface UsePerTypeAssignmentReturn {
  deviceGroups: DeviceTypeGroup[]
  typeConfigs: Map<string, TypeAssignmentConfig>
  globalApplicationId: string
  globalRegionCode: string  // Region code (e.g., "us-west") - required with application_id
  setGlobalApplicationId: (id: string) => void
  updateTypeConfig: (deviceType: string, updates: Partial<TypeAssignmentConfig>) => void
  applyAllAssignments: () => DeviceAssignment[]
  getConfigForType: (deviceType: string) => TypeAssignmentConfig
}

export function usePerTypeAssignment(
  devices: DeviceAssignment[],
  selectedSerials: Set<string>,
  options: OptionsResponse | null,
  setDevices: React.Dispatch<React.SetStateAction<DeviceAssignment[]>>
): UsePerTypeAssignmentReturn {
  const [typeConfigs, setTypeConfigs] = useState<Map<string, TypeAssignmentConfig>>(new Map())
  const [globalApplicationId, setGlobalApplicationIdState] = useState<string>('')
  const [globalRegionCode, setGlobalRegionCode] = useState<string>('')

  // When user selects a region (by application_id), also set the region code
  const setGlobalApplicationId = useCallback((applicationId: string) => {
    setGlobalApplicationIdState(applicationId)
    // Look up the region code from the options
    if (applicationId && options?.regions) {
      const region = options.regions.find(r => r.application_id === applicationId)
      if (region) {
        setGlobalRegionCode(region.region)
        console.log(`Selected region: ${region.display_name} (${region.region}) -> app_id: ${applicationId}`)
      }
    } else {
      setGlobalRegionCode('')
    }
  }, [options])

  // Group selected devices by device_type (and model for switches/gateways)
  // Only include devices that are IN the database (have device_id)
  const deviceGroups = useMemo((): DeviceTypeGroup[] => {
    const groups = new Map<string, { devices: DeviceAssignment[], deviceType: string, model: string | null }>()

    for (const device of devices) {
      // Skip if not selected OR not in database
      if (!selectedSerials.has(device.serial_number)) continue
      if (!device.device_id) continue // Skip devices not in GreenLake

      const type = device.device_type || 'Unknown'

      // For switches and gateways, group by model as well
      let groupKey: string
      let model: string | null = null

      if (MODEL_FILTERED_TYPES.includes(type)) {
        model = device.model || null
        const modelSeries = extractModelSeries(model)
        groupKey = modelSeries ? `${type}_${modelSeries}` : type
      } else {
        groupKey = type
      }

      const existing = groups.get(groupKey)
      if (existing) {
        existing.devices.push(device)
      } else {
        groups.set(groupKey, { devices: [device], deviceType: type, model })
      }
    }

    // Convert to array with subscription filtering
    return Array.from(groups.entries())
      .map(([groupKey, { devices: groupDevices, deviceType, model }]) => {
        // Find compatible subscriptions for this device type
        const category = TYPE_TO_SUBSCRIPTION_CATEGORY[deviceType]
        const modelSeries = extractModelSeries(model)

        const compatibleSubscriptions = options?.subscriptions.filter(sub => {
          // Must match subscription category
          if (!category || sub.subscription_type !== category) {
            return false
          }

          // For model-filtered types, also check tier matches model
          if (MODEL_FILTERED_TYPES.includes(deviceType) && modelSeries) {
            return tierMatchesModel(sub.tier, modelSeries)
          }

          return true
        }) ?? []

        // Build display name
        let displayName = deviceType
        if (MODEL_FILTERED_TYPES.includes(deviceType) && modelSeries) {
          displayName = `${deviceType} ${modelSeries}`
        }

        return {
          deviceType,
          model,
          groupKey,
          displayName,
          devices: groupDevices,
          compatibleSubscriptions,
        }
      })
      .sort((a, b) => b.devices.length - a.devices.length) // Sort by count descending
  }, [devices, selectedSerials, options])

  // Initialize configs when device groups change
  useEffect(() => {
    setTypeConfigs(prev => {
      const newConfigs = new Map(prev)

      // Add configs for new device groups (using groupKey for uniqueness)
      for (const group of deviceGroups) {
        if (!newConfigs.has(group.groupKey)) {
          newConfigs.set(group.groupKey, {
            deviceType: group.groupKey, // Use groupKey as the identifier
            deviceCount: group.devices.length,
            selectedSubscriptionId: null,
            selectedTags: {},
            pendingTagKey: '',
            pendingTagValue: '',
          })
        } else {
          // Update device count for existing groups
          const existing = newConfigs.get(group.groupKey)!
          newConfigs.set(group.groupKey, {
            ...existing,
            deviceCount: group.devices.length,
          })
        }
      }

      // Remove configs for groups no longer present
      for (const key of newConfigs.keys()) {
        if (!deviceGroups.some(g => g.groupKey === key)) {
          newConfigs.delete(key)
        }
      }

      return newConfigs
    })
  }, [deviceGroups])

  // Update a specific type's config
  const updateTypeConfig = useCallback((deviceType: string, updates: Partial<TypeAssignmentConfig>) => {
    console.log('updateTypeConfig called:', deviceType, updates)
    setTypeConfigs(prev => {
      const newConfigs = new Map(prev)
      const existing = newConfigs.get(deviceType)
      if (existing) {
        const updated = { ...existing, ...updates }
        console.log('Updated config:', deviceType, updated)
        newConfigs.set(deviceType, updated)
      } else {
        console.log('No existing config for:', deviceType)
      }
      return newConfigs
    })
  }, [])

  // Get config for a type (with defaults)
  const getConfigForType = useCallback((deviceType: string): TypeAssignmentConfig => {
    return typeConfigs.get(deviceType) ?? {
      deviceType,
      deviceCount: 0,
      selectedSubscriptionId: null,
      selectedTags: {},
      pendingTagKey: '',
      pendingTagValue: '',
    }
  }, [typeConfigs])

  // Apply all assignments to devices and return the updated list
  const applyAllAssignments = useCallback((): DeviceAssignment[] => {
    // DEBUG: Log what we're applying
    console.log('=== applyAllAssignments ===')
    console.log('globalApplicationId:', globalApplicationId)
    console.log('typeConfigs:', Object.fromEntries(typeConfigs))

    const updatedDevices = devices.map(device => {
      // Only update selected devices
      if (!selectedSerials.has(device.serial_number)) return device

      const type = device.device_type || 'Unknown'

      // Build the groupKey to find the correct config
      let groupKey: string
      if (MODEL_FILTERED_TYPES.includes(type)) {
        const modelSeries = extractModelSeries(device.model)
        groupKey = modelSeries ? `${type}_${modelSeries}` : type
      } else {
        groupKey = type
      }

      const config = typeConfigs.get(groupKey)

      const updatedDevice = {
        ...device,
        // Apply global region to all (both application_id AND region code are required by GreenLake API)
        selected_application_id: globalApplicationId || device.selected_application_id,
        selected_region: globalRegionCode || device.selected_region || null,
        // Apply type-specific subscription
        selected_subscription_id: config?.selectedSubscriptionId || device.selected_subscription_id,
        // Merge type-specific tags with existing
        selected_tags: {
          ...device.selected_tags,
          ...(config?.selectedTags || {}),
        },
      }

      // DEBUG: Log first few devices
      if (devices.indexOf(device) < 3) {
        console.log(`Device ${device.serial_number}: app=${updatedDevice.selected_application_id}, region=${updatedDevice.selected_region}, sub=${updatedDevice.selected_subscription_id}`)
      }

      return updatedDevice
    })

    // Update state
    setDevices(updatedDevices)

    // Return the updated devices for immediate use
    return updatedDevices
  }, [devices, setDevices, selectedSerials, typeConfigs, globalApplicationId, globalRegionCode])

  return {
    deviceGroups,
    typeConfigs,
    globalApplicationId,
    globalRegionCode,
    setGlobalApplicationId,
    updateTypeConfig,
    applyAllAssignments,
    getConfigForType,
  }
}
