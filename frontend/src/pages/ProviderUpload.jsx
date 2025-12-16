import { useState, useEffect } from 'react'
import { FileSpreadsheet, FileText, Play } from 'lucide-react'
import axios from 'axios'

export default function ProviderUpload() {
    const [uploads, setUploads] = useState([])
    const [selectedFile, setSelectedFile] = useState(null)

    useEffect(() => {
        loadUploads()
    }, [])

    const loadUploads = () => {
        axios.get('/api/uploads').then(res => setUploads(res.data))
    }

    const handleFileUpload = async (type) => {
        if (!selectedFile) return

        const formData = new FormData()
        formData.append('file', selectedFile)

        try {
            const res = await axios.post(`/api/upload/${type}`, formData)
            alert('File uploaded successfully!')
            setSelectedFile(null)
            loadUploads()
        } catch (error) {
            alert('Upload failed: ' + error.message)
        }
    }

    const startValidation = async () => {
        try {
            const latestUpload = uploads[0]
            if (!latestUpload) {
                alert('No uploads found!')
                return
            }

            const response = await axios.post('/api/validate/start-incremental', {
                upload_id: latestUpload.id
            })
            const sessionId = response.data.session_id

            // Navigate to validation status page with session ID
            window.location.href = `/validation?session=${sessionId}`
        } catch (error) {
            console.error('Validation error:', error)
            alert('Validation failed: ' + (error.response?.data?.detail || error.message))
        }
    }

    return (
        <div>
            <h1>Provider Uploads</h1>
            <p className="subtitle">Upload provider datasets for validation.</p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
                <div className="card" style={{ textAlign: 'center' }}>
                    <FileSpreadsheet size={48} color="#4f46e5" style={{ margin: '0 auto 1rem' }} />
                    <h2>Upload CSV</h2>
                    <p style={{ color: '#6b7280', marginBottom: '1rem' }}>Supported format: .csv — Max size 10MB</p>
                    <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '1.5rem' }}>
                        <strong>Field Requirements:</strong>
                        <ul style={{ textAlign: 'left', marginTop: '0.5rem', paddingLeft: '1.5rem' }}>
                            <li>CSV file with provider records (max 500 rows)</li>
                            <li>Format: Name, Phone, Address, NPI, Specialty</li>
                        </ul>
                    </div>
                    <input type="file" accept=".csv" onChange={(e) => setSelectedFile(e.target.files[0])} style={{ marginBottom: '1rem' }} />
                    <button className="btn-primary" style={{ width: '100%' }} onClick={() => handleFileUpload('csv')}>Upload CSV</button>
                </div>

                <div className="card" style={{ textAlign: 'center' }}>
                    <FileText size={48} color="#4f46e5" style={{ margin: '0 auto 1rem' }} />
                    <h2>Upload PDF</h2>
                    <p style={{ color: '#6b7280', marginBottom: '1rem' }}>Upload provider credentials in PDF format</p>
                    <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '1.5rem' }}>
                        <strong>Field Requirements:</strong>
                        <ul style={{ textAlign: 'left', marginTop: '0.5rem', paddingLeft: '1.5rem' }}>
                            <li>PDF provider credentials: NPI docs, licenses, certificates</li>
                            <li>Max size: 5 MB</li>
                        </ul>
                    </div>
                    <input type="file" accept=".pdf" onChange={(e) => setSelectedFile(e.target.files[0])} style={{ marginBottom: '1rem' }} />
                    <button className="btn-primary" style={{ width: '100%' }} onClick={() => handleFileUpload('pdf')}>Upload PDF</button>
                </div>
            </div>

            <div className="card">
                <h2>Upload History</h2>
                <table>
                    <thead>
                        <tr>
                            <th>File Name</th>
                            <th>Type</th>
                            <th>Timestamp</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {uploads.map(upload => (
                            <tr key={upload.id}>
                                <td>{upload.filename}</td>
                                <td>{upload.type}</td>
                                <td>{upload.timestamp}</td>
                                <td>
                                    <span className={`status-badge status-${upload.status.toLowerCase()}`}>
                                        {upload.status}
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                <button
                    className="btn-primary"
                    style={{ width: '100%', marginTop: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
                    onClick={startValidation}
                >
                    <Play size={18} />
                    Start Validation Workflow
                </button>
            </div>
        </div>
    )
}
