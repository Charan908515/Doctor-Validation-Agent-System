import { useState, useEffect } from 'react'
import { Search, RefreshCw, CheckCircle, Loader } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import axios from 'axios'

export default function ValidationStatus() {
    const [providers, setProviders] = useState([])
    const [search, setSearch] = useState('')
    const [statusFilter, setStatusFilter] = useState('All')
    const [page, setPage] = useState(1)
    const navigate = useNavigate()
    const [searchParams] = useSearchParams()

    // Progress tracking
    const [validationProgress, setValidationProgress] = useState(null)
    const [isPolling, setIsPolling] = useState(false)
    const sessionId = searchParams.get('session')

    useEffect(() => {
        loadProviders()
    }, [statusFilter, search, page])

    // Poll for progress if session ID is present
    useEffect(() => {
        if (sessionId) {
            setIsPolling(true)
            pollProgress()
        }
    }, [sessionId])

    const pollProgress = async () => {
        try {
            const res = await axios.get(`/api/validation/progress/${sessionId}`)
            setValidationProgress(res.data)

            // Continue polling if still in progress
            if (res.data.status === 'in_progress') {
                setTimeout(pollProgress, 2000) // Poll every 2 seconds
                loadProviders() // Refresh provider list
            } else {
                setIsPolling(false)
                loadProviders() // Final refresh
            }
        } catch (error) {
            console.error('Failed to fetch progress:', error)
            setIsPolling(false)
        }
    }

    const loadProviders = async () => {
        try {
            const res = await axios.get('/api/validation/status', {
                params: { status: statusFilter !== 'All' ? statusFilter : undefined, search, skip: (page - 1) * 10, limit: 10 }
            })
            setProviders(res.data.data || [])
        } catch (error) {
            console.error('Failed to load providers:', error)
        }
    }

    const getStatusClass = (status) => {
        if (status === 'verified') return 'status-validated'
        if (status === 'updated details') return 'status-progress'
        if (status === 'human verification needed') return 'status-failed'
        return 'status-pending'
    }

    // Format status for display with proper capitalization
    const formatStatus = (status) => {
        if (!status) return 'Pending'
        // Capitalize each word
        return status.split(' ').map(word =>
            word.charAt(0).toUpperCase() + word.slice(1)
        ).join(' ')
    }

    return (
        <div>
            <h1>Validation Status</h1>

            {/* Progress Bar */}
            {isPolling && validationProgress && (
                <div className="card" style={{ marginBottom: '2rem', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
                    <div style={{ color: 'white' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                            <Loader size={24} className="spin" />
                            <div>
                                <h3 style={{ margin: 0, fontSize: '1.125rem' }}>Validation In Progress...</h3>
                                <p style={{ margin: '0.25rem 0 0 0', opacity: 0.9, fontSize: '0.875rem' }}>
                                    {validationProgress.status_message || `Processing: ${validationProgress.current_hospital || 'Starting...'}`}
                                </p>
                            </div>
                        </div>

                        {/* Progress Bar */}
                        <div style={{
                            background: 'rgba(255,255,255,0.2)',
                            borderRadius: '9999px',
                            height: '12px',
                            marginBottom: '1rem',
                            overflow: 'hidden'
                        }}>
                            <div style={{
                                background: 'white',
                                height: '100%',
                                width: `${validationProgress.progress_percentage}%`,
                                transition: 'width 0.5s ease',
                                borderRadius: '9999px'
                            }}></div>
                        </div>

                        {/* Stats */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', fontSize: '0.875rem' }}>
                            <div>
                                <div style={{ opacity: 0.9 }}>Progress</div>
                                <div style={{ fontSize: '1.25rem', fontWeight: 'bold' }}>
                                    {validationProgress.completed_hospitals}/{validationProgress.total_hospitals}
                                </div>
                            </div>
                            <div>
                                <div style={{ opacity: 0.9 }}>Verified</div>
                                <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#10b981' }}>
                                    {validationProgress.verified_count}
                                </div>
                            </div>
                            <div>
                                <div style={{ opacity: 0.9 }}>Updated</div>
                                <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#f59e0b' }}>
                                    {validationProgress.updated_count}
                                </div>
                            </div>
                            <div>
                                <div style={{ opacity: 0.9 }}>Needs Review</div>
                                <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#ef4444' }}>
                                    {validationProgress.needs_review_count}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* Completion Message */}
            {validationProgress && validationProgress.status === 'completed' && (
                <div className="card" style={{ marginBottom: '2rem', background: '#10b981', color: 'white' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <CheckCircle size={32} />
                        <div>
                            <h3 style={{ margin: 0 }}>Validation Complete!</h3>
                            <p style={{ margin: '0.25rem 0 0 0', opacity: 0.9 }}>
                                Processed {validationProgress.total_records} records from {validationProgress.total_hospitals} hospitals
                            </p>
                        </div>
                    </div>
                </div>
            )}

            <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', alignItems: 'center' }}>
                <div style={{ flex: 1, position: 'relative' }}>
                    <input
                        type="text"
                        placeholder="Search provider..."
                        className="search-input"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                </div>
                <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ width: '200px' }}>
                    <option>All</option>
                    <option>verified</option>
                    <option>updated details</option>
                    <option>human verification needed</option>
                </select>
                <button onClick={loadProviders} style={{ padding: '0.625rem', background: 'white', border: '1px solid #e5e7eb' }}>
                    <RefreshCw size={20} />
                </button>
            </div>

            <div className="card">
                <table>
                    <thead>
                        <tr>
                            <th>Provider Name</th>
                            <th>Validation Status</th>
                            <th>Confidence Score</th>
                            <th>Flags</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {providers.map(provider => (
                            <tr key={provider.id}>
                                <td>{provider.provider_name}</td>
                                <td>
                                    <span className={`status-badge ${getStatusClass(provider.status)}`}>
                                        {formatStatus(provider.status)}
                                    </span>
                                </td>
                                <td>{provider.confidence_score ? `${provider.confidence_score}%` : '—'}</td>
                                <td style={{ fontSize: '0.875rem', color: '#6b7280' }}>
                                    {provider.flags || '—'}
                                </td>
                                <td>
                                    <button
                                        onClick={() => navigate(`/comparison/${provider.id}`)}
                                        style={{ color: '#4f46e5', background: 'none', padding: '0', fontWeight: 500 }}
                                    >
                                        View Details
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1.5rem' }}>
                    <button className="btn-secondary" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>
                        Previous
                    </button>
                    <span style={{ fontSize: '0.875rem', color: '#6b7280' }}>Page {page}</span>
                    <button className="btn-secondary" onClick={() => setPage(p => p + 1)}>
                        Next
                    </button>
                </div>
            </div>
        </div>
    )
}
