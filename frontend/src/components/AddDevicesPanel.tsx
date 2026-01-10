import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Plus, AlertTriangle, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import toast from 'react-hot-toast'
import { assignmentApi } from '../api/client'
import type { DeviceAssignment, AddDevicesResponse } from '../types'

interface AddDevicesPanelProps {
  devices: DeviceAssignment[]
  onDevicesAdded?: () => void
}

export function AddDevicesPanel({ devices, onDevicesAdded }: AddDevicesPanelProps) {
  // Filter devices that are not in GreenLake and have MAC addresses
  const missingDevices = devices.filter(d => !d.device_id)
  const devicesWithMac = missingDevices.filter(d => d.mac_address)
  const devicesWithoutMac = missingDevices.filter(d => !d.mac_address)

  const [selectedSerials, setSelectedSerials] = useState<Set<string>>(
    new Set(devicesWithMac.map(d => d.serial_number))
  )

  const addDevicesMutation = useMutation({
    mutationFn: async () => {
      const devicesToAdd = devicesWithMac
        .filter(d => selectedSerials.has(d.serial_number))
        .map(d => ({
          serial_number: d.serial_number,
          mac_address: d.mac_address!,
          device_type: 'NETWORK', // Network devices by default
        }))

      return assignmentApi.addDevices({
        devices: devicesToAdd,
        wait_for_completion: true,
      })
    },
    onSuccess: (data: AddDevicesResponse) => {
      if (data.success) {
        toast.success(`Successfully added ${data.devices_added} device(s) to GreenLake`)
      } else {
        toast.error(`Added ${data.devices_added} devices, ${data.devices_failed} failed`)
      }
      onDevicesAdded?.()
    },
    onError: (error: Error) => {
      toast.error(`Failed to add devices: ${error.message}`)
    },
  })

  const toggleDevice = (serial: string) => {
    setSelectedSerials(prev => {
      const next = new Set(prev)
      if (next.has(serial)) {
        next.delete(serial)
      } else {
        next.add(serial)
      }
      return next
    })
  }

  const selectAll = () => {
    setSelectedSerials(new Set(devicesWithMac.map(d => d.serial_number)))
  }

  const deselectAll = () => {
    setSelectedSerials(new Set())
  }

  if (missingDevices.length === 0) {
    return null
  }

  return (
    <div className="card" data-testid="add-devices-panel">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-amber-500/20">
          <AlertTriangle className="w-5 h-5 text-amber-400" aria-hidden="true" />
        </div>
        <div>
          <h3 className="text-lg font-medium text-white">Devices Not in GreenLake</h3>
          <p className="text-sm text-slate-400">
            {missingDevices.length} device(s) from your upload were not found in GreenLake
          </p>
        </div>
      </div>

      {devicesWithMac.length > 0 && (
        <div className="mb-6">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-medium text-slate-300">
              Ready to Add ({devicesWithMac.length})
            </h4>
            <div className="flex gap-2">
              <button
                onClick={selectAll}
                className="text-xs text-sky-400 hover:text-sky-300"
              >
                Select All
              </button>
              <span className="text-slate-600">|</span>
              <button
                onClick={deselectAll}
                className="text-xs text-slate-400 hover:text-slate-300"
              >
                Deselect All
              </button>
            </div>
          </div>

          <div className="max-h-48 overflow-y-auto rounded-lg border border-slate-700 bg-slate-800/50">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-800">
                <tr className="border-b border-slate-700">
                  <th className="w-8 px-3 py-2"></th>
                  <th className="text-left px-3 py-2 text-slate-400 font-medium">Serial Number</th>
                  <th className="text-left px-3 py-2 text-slate-400 font-medium">MAC Address</th>
                  <th className="text-left px-3 py-2 text-slate-400 font-medium">Type</th>
                </tr>
              </thead>
              <tbody>
                {devicesWithMac.map(device => (
                  <tr
                    key={device.serial_number}
                    className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer"
                    onClick={() => toggleDevice(device.serial_number)}
                  >
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={selectedSerials.has(device.serial_number)}
                        onChange={() => toggleDevice(device.serial_number)}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-700 text-hpe-green focus:ring-hpe-green focus:ring-offset-0"
                        onClick={e => e.stopPropagation()}
                      />
                    </td>
                    <td className="px-3 py-2 font-mono text-slate-300">{device.serial_number}</td>
                    <td className="px-3 py-2 font-mono text-slate-400">{device.mac_address}</td>
                    <td className="px-3 py-2 text-slate-400">{device.device_type || 'NETWORK'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <button
            onClick={() => addDevicesMutation.mutate()}
            disabled={selectedSerials.size === 0 || addDevicesMutation.isPending}
            className={clsx(
              'mt-4 btn w-full flex items-center justify-center gap-2',
              selectedSerials.size > 0 && !addDevicesMutation.isPending
                ? 'btn-primary'
                : 'btn-secondary opacity-50 cursor-not-allowed'
            )}
            data-testid="add-devices-btn"
          >
            {addDevicesMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                Adding Devices...
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" aria-hidden="true" />
                Add {selectedSerials.size} Device(s) to GreenLake
              </>
            )}
          </button>

          {/* Results */}
          {addDevicesMutation.isSuccess && (
            <div className="mt-4 p-4 rounded-lg bg-slate-800/50 border border-slate-700">
              <h5 className="font-medium text-slate-300 mb-3">Add Results</h5>
              <div className="space-y-2">
                {addDevicesMutation.data.results.map(result => (
                  <div
                    key={result.serial_number}
                    className="flex items-center gap-2 text-sm"
                  >
                    {result.success ? (
                      <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                    )}
                    <span className="font-mono text-slate-300">{result.serial_number}</span>
                    {!result.success && (
                      <span className="text-rose-400 text-xs">{result.error}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {devicesWithoutMac.length > 0 && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-4">
          <h4 className="font-medium text-rose-400 mb-2">
            Cannot Add ({devicesWithoutMac.length})
          </h4>
          <p className="text-sm text-rose-300/80 mb-3">
            These devices are missing MAC addresses, which are required to add NETWORK devices to GreenLake.
          </p>
          <ul className="text-sm text-rose-300/70 font-mono space-y-1">
            {devicesWithoutMac.slice(0, 5).map(d => (
              <li key={d.serial_number}>• {d.serial_number}</li>
            ))}
            {devicesWithoutMac.length > 5 && (
              <li className="text-rose-400">... and {devicesWithoutMac.length - 5} more</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}
