import { Link, useLocation } from 'react-router-dom'
import { Home, Upload, CheckCircle, GitCompare, FileText } from 'lucide-react'

export default function Sidebar() {
    const location = useLocation()

    const isActive = (path) => location.pathname === path

    const navItems = [
        { path: '/', label: 'Dashboard', icon: Home },
        { path: '/upload', label: 'Provider Upload', icon: Upload },
        { path: '/validation', label: 'Validation Status', icon: CheckCircle },
        { path: '/view-data', label: 'View Data', icon: FileText },
        { path: '/comparison', label: 'Comparison', icon: GitCompare }
    ]

    return (
        <aside style={styles.sidebar}>
            <div style={styles.header}>
                <div style={styles.logo}>
                    <div style={styles.logoIcon}>⚕</div>
                    <span style={styles.logoText}>Solution Seekers</span>
                </div>
            </div>

            <nav style={styles.nav}>
                {navItems.map(({ path, label, icon: Icon }) => (
                    <Link
                        key={path}
                        to={path}
                        style={{
                            ...styles.navItem,
                            ...(isActive(path) ? styles.navItemActive : {})
                        }}
                    >
                        <Icon size={20} />
                        <span>{label}</span>
                    </Link>
                ))}
            </nav>
        </aside>
    )
}

const styles = {
    sidebar: {
        position: 'fixed',
        left: 0,
        top: 0,
        width: '250px',
        height: '100vh',
        background: 'white',
        borderRight: '1px solid #e5e7eb',
        padding: '1.5rem 0',
        zIndex: 10
    },
    header: {
        padding: '0 1.5rem 2rem'
    },
    logo: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem'
    },
    logoIcon: {
        width: '32px',
        height: '32px',
        borderRadius: '8px',
        background: '#4f46e5',
        color: 'white',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '1.25rem'
    },
    logoText: {
        fontSize: '1.125rem',
        fontWeight: 600,
        color: '#1a202c'
    },
    nav: {
        display: 'flex',
        flexDirection: 'column'
    },
    navItem: {
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.75rem 1.5rem',
        color: '#6b7280',
        textDecoration: 'none',
        transition: 'all 0.2s',
        fontSize: '0.938rem'
    },
    navItemActive: {
        background: '#ede9fe',
        color: '#4f46e5',
        borderRight: '3px solid #4f46e5'
    }
}
