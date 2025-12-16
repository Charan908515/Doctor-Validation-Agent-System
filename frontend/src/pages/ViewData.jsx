import { useEffect, useState } from 'react'
import { FileText, ChevronDown } from 'lucide-react'
import axios from 'axios'

export default function ViewData() {
    const [uploads, setUploads] = useState([])
    const [selectedUpload, setSelectedUpload] = useState(null)
    const [csvData, setCsvData] = useState(null)
    const [loading, setLoading] = useState(false)
    const [currentPage, setCurrentPage] = useState(1)
    const rowsPerPage = 20

    useEffect(() => {
        loadUploads()
    }, [])

    const loadUploads = async () => {
        try {
            const res = await axios.get('/api/uploads')
            setUploads(res.data)
            if (res.data.length > 0) {
                setSelectedUpload(res.data[0].id)
            }
        } catch (error) {
            console.error('Failed to load uploads:', error)
        }
    }

    const loadCsvData = async (uploadId) => {
        if (!uploadId) return

        setLoading(true)
        try {
            const res = await axios.get(`/api/uploaded-data/${uploadId}`)
            setCsvData(res.data)
            setCurrentPage(1)
        } catch (error) {
            console.error('Failed to load CSV data:', error)
            alert('Failed to load CSV data: ' + (error.response?.data?.detail || error.message))
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (selectedUpload) {
            loadCsvData(selectedUpload)
        }
    }, [selectedUpload])

    // Pagination
    const totalPages = csvData ? Math.ceil(csvData.data.length / rowsPerPage) : 0
    const startIdx = (currentPage - 1) * rowsPerPage
    const endIdx = startIdx + rowsPerPage
    const paginatedData = csvData?.data.slice(startIdx, endIdx) || []

    return (
        <div>
            <h1>View Uploaded Data</h1>
            <p className="subtitle">Browse and inspect uploaded CSV files.</p>

            <div className="card" style={{ marginBottom: '2rem' }}>
                <div style={{ marginBottom: '1.5rem' }}>
                    <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>
                        Select Upload
                    </label>
                    <select
                        value={selectedUpload || ''}
                        onChange={(e) => setSelectedUpload(parseInt(e.target.value))}
                        style={{ width: '100%', maxWidth: '400px' }}
                    >
                        {uploads.map(upload => (
                            <option key={upload.id} value={upload.id}>
                                {upload.filename} - {upload.timestamp} ({upload.record_count} records)
                            </option>
                        ))}
                    </select>
                </div>

                {loading && (
                    <div style={{ textAlign: 'center', padding: '2rem', color: '#6b7280' }}>
                        Loading data...
                    </div>
                )}

                {!loading && csvData && (
                    <>
                        <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                <FileText size={16} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '0.5rem' }} />
                                <strong>{csvData.filename}</strong> - {csvData.record_count} records
                            </div>
                            <div style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                Uploaded: {new Date(csvData.uploaded_at).toLocaleString()}
                            </div>
                        </div>

                        <div style={{ overflowX: 'auto' }}>
                            <table>
                                <thead>
                                    <tr>
                                        {csvData.columns.map((col, idx) => (
                                            <th key={idx}>{col}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {paginatedData.map((row, idx) => (
                                        <tr key={idx}>
                                            {csvData.columns.map((col, colIdx) => (
                                                <td key={colIdx}>{row[col] || '—'}</td>
                                            ))}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>

                        {totalPages > 1 && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
                                <button
                                    className="btn-secondary"
                                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                    disabled={currentPage === 1}
                                >
                                    Previous
                                </button>
                                <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                    Page {currentPage} of {totalPages}
                                </span>
                                <button
                                    className="btn-secondary"
                                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                    disabled={currentPage === totalPages}
                                >
                                    Next
                                </button>
                            </div>
                        )}
                    </>
                )}

                {!loading && !csvData && (
                    <div style={{ textAlign: 'center', padding: '2rem', color: '#6b7280' }}>
                        No data to display
                    </div>
                )}
            </div>
        </div>
    )
}
