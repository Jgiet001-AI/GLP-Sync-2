import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileSpreadsheet, AlertCircle } from 'lucide-react'
import clsx from 'clsx'

interface FileUploadProps {
  onUpload: (file: File) => void
  isUploading: boolean
}

export function FileUpload({ onUpload, isUploading }: FileUploadProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) {
        onUpload(acceptedFiles[0])
      }
    },
    [onUpload]
  )

  const { getRootProps, getInputProps, isDragActive, fileRejections } =
    useDropzone({
      onDrop,
      accept: {
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
        'application/vnd.ms-excel': ['.xls'],
        'text/csv': ['.csv'],
        'application/csv': ['.csv'],
      },
      maxFiles: 1,
      disabled: isUploading,
    })

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div
        {...getRootProps()}
        className={clsx(
          'border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all duration-200',
          isDragActive
            ? 'border-hpe-green bg-hpe-green/5'
            : 'border-slate-600 hover:border-hpe-green hover:bg-slate-800/50',
          isUploading && 'opacity-50 cursor-not-allowed'
        )}
        role="button"
        aria-label="File upload dropzone. Drop an Excel or CSV file, or click to browse"
        data-testid="file-upload-dropzone"
      >
        <input {...getInputProps()} data-testid="file-upload-input" aria-label="File input" />

        <div className="flex flex-col items-center gap-4">
          {isUploading ? (
            <>
              <div
                className="animate-spin rounded-full h-12 w-12 border-4 border-hpe-green border-t-transparent"
                role="status"
                aria-label="Processing file"
              />
              <p className="text-lg text-slate-300">Processing file...</p>
            </>
          ) : isDragActive ? (
            <>
              <Upload className="w-12 h-12 text-hpe-green" aria-hidden="true" />
              <p className="text-lg text-hpe-green font-medium">
                Drop the file here
              </p>
            </>
          ) : (
            <>
              <FileSpreadsheet className="w-12 h-12 text-slate-400" aria-hidden="true" />
              <div>
                <p className="text-lg text-slate-200 font-medium">
                  Drop an Excel or CSV file here
                </p>
                <p className="text-sm text-slate-400 mt-1">
                  or click to browse
                </p>
              </div>
            </>
          )}
        </div>
      </div>

      {fileRejections.length > 0 && (
        <div
          className="mt-4 p-4 bg-rose-500/10 border border-rose-500/30 rounded-lg"
          role="alert"
          data-testid="file-upload-error"
        >
          <div className="flex items-center gap-2 text-rose-400">
            <AlertCircle className="w-5 h-5" aria-hidden="true" />
            <span className="font-medium">Invalid file format</span>
          </div>
          <p className="mt-1 text-sm text-rose-300">
            Please upload an Excel (.xlsx, .xls) or CSV (.csv) file
          </p>
        </div>
      )}

      <div className="mt-6 p-4 bg-sky-500/10 border border-sky-500/30 rounded-lg">
        <h3 className="font-medium text-sky-300">Expected File Format</h3>
        <div className="mt-2 overflow-x-auto">
          <table className="text-sm text-sky-200" data-testid="file-format-table">
            <thead>
              <tr className="border-b border-sky-500/30">
                <th className="px-4 py-2 text-left text-sky-300">Serial Number</th>
                <th className="px-4 py-2 text-left text-sky-300">MAC Address</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="px-4 py-2">SN12345</td>
                <td className="px-4 py-2">00:1B:44:11:3A:B7</td>
              </tr>
              <tr>
                <td className="px-4 py-2">SN67890</td>
                <td className="px-4 py-2 text-slate-500">(optional)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
