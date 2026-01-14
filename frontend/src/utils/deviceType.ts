/**
 * Normalize device type for display purposes.
 * IAP and AP are the same device type and should both display as "AP".
 *
 * @param deviceType - The raw device type from the API
 * @returns The normalized device type for display
 */
export function normalizeDeviceType(deviceType: string | null | undefined): string {
  if (!deviceType) return 'UNKNOWN'

  // Merge IAP and AP into single AP category
  if (deviceType === 'IAP') return 'AP'

  return deviceType
}
