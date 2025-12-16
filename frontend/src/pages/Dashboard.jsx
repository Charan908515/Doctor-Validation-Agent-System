import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Users, CheckCircle, AlertTriangle, Flag, Download } from 'lucide-react'
import { Line } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement } from 'chart.js'
import axios from 'axios'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement)

export default function Dashboard() {
    const [stats, setStats] = useState(null)
    const [recentIssues, setRecentIssues] = useState([])
    const [trendData, setTrendData] = useState({ labels: [], data: [] })

    useEffect(() => {
        loadDashboardData()
    }, [])

    const loadDashboardData = async () => {
        try {
            // Load stats
            const statsRes = await axios.get('/api/dashboard/stats')
            setStats(statsRes.data)

            // Load recent issues (providers with errors)
            const issuesRes = await axios.get('/api/validation/status', {
                params: { status: 'human verification needed', limit: 5 }
            })
            setRecentIssues(issuesRes.data.data || [])

            // Load error trends
            const trendsRes = await axios.get('/api/dashboard/trends')
            setTrendData(trendsRes.data)
        } catch (error) {
            console.error('Failed to load dashboard data:', error)
        }
    }

    const chartData = {
        labels: trendData.labels,
        datasets: [{
            data: trendData.data,
            borderColor: '#4f46e5',
            tension: 0.4
        }]
    }

    return (
        <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
                <h1>Dashboard Overview</h1>
                <button className="btn-primary" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Download size={18} />
                    Download PDF/CSV
                </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.5rem', marginBottom: '2rem' }}>
                <StatCard
                    title="Total Providers"
                    value={stats?.total_providers || 0}
                    icon={<Users />}
                />
                <StatCard
                    title="Validated Providers"
                    value={stats?.validated_providers || 0}
                    icon={<CheckCircle />}
                    positive
                />
                <StatCard
                    title="Errors Detected"
                    value={stats?.errors_detected || 0}
                    icon={<AlertTriangle />}
                />
                <StatCard
                    title="Flagged Records"
                    value={stats?.flagged_records || 0}
                    icon={<Flag />}
                />
            </div>

            <div className="card" style={{ marginBottom: '2rem' }}>
                <h2>Error Trends</h2>
                <Line data={chartData} options={{ plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }} />
            </div>

            <div className="card">
                <h2>Recent Issues</h2>
                {recentIssues.length > 0 ? (
                    <table>
                        <thead>
                            <tr>
                                <th>Provider Name</th>
                                <th>Hospital</th>
                                <th>Issue Type</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {recentIssues.map(provider => (
                                <IssueRow
                                    key={provider.id}
                                    name={provider.provider_name}
                                    hospital={provider.hospital}
                                    issue={provider.flags || 'Verification needed'}
                                    status={provider.status}
                                />
                            ))}
                        </tbody>
                    </table>
                ) : (
                    <p style={{ color: '#6b7280', textAlign: 'center', padding: '2rem' }}>
                        No recent issues found
                    </p>
                )}
            </div>
        </div>
    )
}

function StatCard({ title, value, icon, positive }) {
    return (
        <div className="card" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <div>
                <div style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.5rem' }}>{title}</div>
                <div style={{ fontSize: '2rem', fontWeight: 700 }}>{value}</div>
            </div>
            <div style={{ color: '#4f46e5' }}>{icon}</div>
        </div>
    )
}

function IssueRow({ name, hospital, issue, status }) {
    return (
        <tr>
            <td>{name}</td>
            <td>{hospital}</td>
            <td>{issue}</td>
            <td>
                <span className="status-badge status-failed">
                    Needs Review
                </span>
            </td>
        </tr>
    )
}
