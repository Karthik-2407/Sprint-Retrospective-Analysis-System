"""Modern design system and CSS styling for the DORA Platform dashboard.

Includes modern card shells, status-coded badges, elevation, typography,
and responsive container layouts.
"""

# ruff: noqa: E501, W293

CSS_STYLES = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root {
        --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        --font-mono: 'JetBrains Mono', monospace;
        
        --bg-main: #f8fafc;
        --card-bg: #ffffff;
        --card-border: #e2e8f0;
        --card-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
        --card-hover-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04);
        
        --text-primary: #0f172a;
        --text-secondary: #475569;
        --text-muted: #64748b;
        --text-light: #94a3b8;
        
        --primary-blue: #2563eb;
        --primary-blue-soft: #eff6ff;
        --primary-blue-border: #bfdbfe;
        
        --accent-purple: #7c3aed;
        --accent-purple-soft: #f5f3ff;
        --accent-purple-border: #ddd6fe;
        
        --status-ok-bg: #ecfdf5;
        --status-ok-text: #059669;
        --status-ok-border: #a7f3d0;
        
        --status-no-events-bg: #fffbeb;
        --status-no-events-text: #d97706;
        --status-no-events-border: #fde68a;
        
        --status-undetectable-bg: #fef2f2;
        --status-undetectable-text: #dc2626;
        --status-undetectable-border: #fecaca;
        
        --status-insufficient-bg: #f1f5f9;
        --status-insufficient-text: #475569;
        --status-insufficient-border: #cbd5e1;
        
        --status-partial-bg: #eff6ff;
        --status-partial-text: #2563eb;
        --status-partial-border: #bfdbfe;
    }

    html, body, [data-testid="stAppViewContainer"] {
        font-family: var(--font-sans);
        background-color: var(--bg-main);
        color: var(--text-primary);
    }

    /* Streamlit top header cleanup */
    header[data-testid="stHeader"] {
        background-color: rgba(248, 250, 252, 0.85);
        backdrop-filter: blur(8px);
    }

    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1329 0%, #111d38 100%);
        border-right: 1px solid #1e293b;
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] span {
        color: #f1f5f9 !important;
    }

    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stRadio label {
        color: #94a3b8 !important;
        font-weight: 600;
        font-size: 0.82rem;
        letter-spacing: 0.03em;
        text-transform: uppercase;
    }

    /* Top Hero Banner */
    .top-hero {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-radius: 16px;
        padding: 1.5rem 1.8rem;
        color: #ffffff;
        margin-bottom: 1.5rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        display: flex;
        justify-content: space-between;
        align-items: center;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }

    .hero-title {
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0;
        color: #ffffff;
    }

    .hero-subtitle {
        color: #94a3b8;
        font-size: 0.9rem;
        margin-top: 0.35rem;
        margin-bottom: 0;
    }

    .hero-tag {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        background: rgba(37, 99, 235, 0.2);
        color: #60a5fa;
        border: 1px solid rgba(96, 165, 250, 0.3);
    }

    /* Metric Cards */
    .metric-card {
        background-color: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        padding: 1.25rem 1.35rem;
        box-shadow: var(--card-shadow);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
        margin-bottom: 1rem;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        position: relative;
        overflow: hidden;
    }

    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: var(--card-hover-shadow);
        border-color: #cbd5e1;
    }

    .metric-card-top-bar {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 4px;
    }

    .card-header-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 0.75rem;
        margin-bottom: 0.8rem;
    }

    .metric-category-title {
        font-size: 0.8rem;
        font-weight: 700;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin: 0;
    }

    .metric-main-value {
        font-size: 2.15rem;
        font-weight: 800;
        line-height: 1.1;
        letter-spacing: -0.04em;
        color: var(--text-primary);
        margin: 0.2rem 0;
        font-feature-settings: "tnum";
    }

    .metric-unit {
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--text-muted);
        margin-left: 0.35rem;
    }

    .metric-footer {
        border-top: 1px solid #f1f5f9;
        margin-top: 0.85rem;
        padding-top: 0.65rem;
        font-size: 0.8rem;
        color: var(--text-secondary);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.4rem;
    }

    .metric-ci-pill {
        font-family: var(--font-mono);
        font-size: 0.75rem;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 0.15rem 0.5rem;
        border-radius: 6px;
        color: #334155;
    }

    .metric-n-badge {
        font-family: var(--font-mono);
        font-size: 0.75rem;
        font-weight: 600;
        padding: 0.15rem 0.45rem;
        border-radius: 6px;
    }

    .n-pass {
        background-color: #ecfdf5;
        color: #059669;
        border: 1px solid #a7f3d0;
    }

    .n-fail {
        background-color: #f1f5f9;
        color: #64748b;
        border: 1px solid #cbd5e1;
    }

    /* Status Badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        padding: 0.28rem 0.65rem;
        border-radius: 9999px;
        white-space: nowrap;
    }

    .status-badge.ok {
        background-color: var(--status-ok-bg);
        color: var(--status-ok-text);
        border: 1px solid var(--status-ok-border);
    }

    .status-badge.no_events {
        background-color: var(--status-no-events-bg);
        color: var(--status-no-events-text);
        border: 1px solid var(--status-no-events-border);
    }

    .status-badge.undetectable {
        background-color: var(--status-undetectable-bg);
        color: var(--status-undetectable-text);
        border: 1px solid var(--status-undetectable-border);
    }

    .status-badge.insufficient_sample {
        background-color: var(--status-insufficient-bg);
        color: var(--status-insufficient-text);
        border: 1px solid var(--status-insufficient-border);
    }

    .status-badge.partial_data {
        background-color: var(--status-partial-bg);
        color: var(--status-partial-text);
        border: 1px solid var(--status-partial-border);
    }

    /* Section Subheading */
    .section-header-box {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-top: 1.5rem;
        margin-bottom: 0.9rem;
    }

    .section-header-box h3 {
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--text-primary);
        margin: 0;
    }

    .section-header-badge {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        padding: 0.2rem 0.55rem;
        border-radius: 6px;
        background: #f1f5f9;
        color: #475569;
        letter-spacing: 0.05em;
    }

    /* Evidence Drawer & Tables */
    .evidence-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    .def-version-tag {
        font-family: var(--font-mono);
        font-size: 0.7rem;
        font-weight: 600;
        background: #f8fafc;
        border: 1px solid #cbd5e1;
        padding: 0.15rem 0.45rem;
        border-radius: 4px;
        color: #475569;
    }

    /* Anti-gaming alert banner */
    .gaming-alert {
        background: #fffbeb;
        border-left: 4px solid #f59e0b;
        padding: 0.85rem 1.1rem;
        border-radius: 8px;
        color: #92400e;
        font-size: 0.88rem;
        margin-bottom: 1rem;
    }

    /* Pulse dot */
    .pulse-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .pulse-green { background-color: #10b981; box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2); }
    .pulse-amber { background-color: #f59e0b; box-shadow: 0 0 0 2px rgba(245, 158, 11, 0.2); }
    .pulse-red { background-color: #ef4444; box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2); }
    .pulse-blue { background-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); }
</style>
"""
