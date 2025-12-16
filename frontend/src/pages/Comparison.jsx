import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle } from 'lucide-react'
import axios from 'axios'

export default function Comparison() {
    const { id } = useParams()
    const navigate = useNavigate()
    const [data, setData] = useState(null)

    useEffect(() => {
        if (id) {
            axios.get(`/api/validation/${id}`)
                .then(res => setData(res.data))
                .catch(err => console.error('Failed to load comparison:', err))
        }
    }, [id])

    const handleAccept = async () => {
        try {
            await axios.put(`/api/validation/${id}/accept`)
            alert('Changes accepted!')
            navigate('/validation')
        } catch (error) {
            alert('Failed to accept changes')
        }
    }

    const handleReject = async () => {
        try {
            await axios.put(`/api/validation/${id}/reject`)
            alert('Changes rejected!')
            navigate('/validation')
        } catch (error) {
            alert('Failed to reject changes')
        }
    }

    if (!data) return <div>Loading...</div>

    const isDifferent = (field) => {
        return data.original[field] !== data.validated[field]
    }

    return (
        <div>
            <h1>Compare Provider Data</h1>
            <p className="subtitle">
                Check and compare the original provider details with the updated validated details. Any field that looks different will be highlighted so you can review and fix it.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
                <div className="card">
                    <h2 style={{ marginBottom: '1.5rem' }}>Original Data</h2>
                    <DataPanel data={data.original} differences={data.validated} />
                </div>

                <div className="card">
                    <h2 style={{ marginBottom: '1.5rem' }}>Validated Data</h2>
                    <DataPanel data={data.validated} differences={data.original} highlight />
                </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
                <button className="btn-secondary" onClick={handleReject} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <XCircle size={18} />
                    Reject Changes
                </button>
                <button className="btn-primary" onClick={handleAccept} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <CheckCircle size={18} />
                    Accept Changes
                </button>
            </div>
        </div>
    )
}

function DataPanel({ data, differences, highlight }) {
    const fields = [
        { key: 'name', label: 'Name' },
        { key: 'phone', label: 'Phone Number' },
        { key: 'address', label: 'Address' },
        { key: 'npi', label: 'NPI Number' },
        { key: 'education', label: 'Education' },
        { key: 'specialties', label: 'Specialties' }
    ]

    return (
        <div>
            {fields.map(({ key, label }) => {
                const isDiff = data[key] !== differences[key]
                return (
                    <div key={key} style={{ marginBottom: '1.5rem' }}>
                        <div style={{ fontSize: '0.875rem', fontWeight: 600, color: '#374151', marginBottom: '0.5rem' }}>
                            {label}
                        </div>
                        <div style={{
                            padding: '0.75rem',
                            border: `2px solid ${isDiff && highlight ? '#ef4444' : '#e5e7eb'}`,
                            borderRadius: '6px',
                            background: isDiff && highlight ? '#fef2f2' : 'white'
                        }}>
                            {data[key] || '—'}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}
