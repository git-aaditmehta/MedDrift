import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import sqlalchemy
from config import DB_CONFIG, TARGET_DRUGS, DRUG_CATEGORIES
import logging
import os

logger = logging.getLogger(__name__)

def get_engine():
    url = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )
    return sqlalchemy.create_engine(url)

# ── Color scheme ──────────────────────────────────────────
COLORS = {
    'humira':    '#2196F3',   # blue
    'zantac':    '#F44336',   # red
    'jardiance': '#4CAF50',   # green
    'high':      '#F44336',
    'medium':    '#FF9800',
    'low':       '#9E9E9E',
    'background':'#0F1117',
    'card':      '#1E2130',
    'text':      '#FFFFFF',
    'grid':      '#2D3250'
}

DRUG_COLORS = {
    'humira': COLORS['humira'],
    'zantac': COLORS['zantac'],
    'jardiance': COLORS['jardiance']
}

def load_data():
    """Load all required data."""
    engine = get_engine()
    
    # Master signals
    signals = pd.read_csv('outputs/master_signals.csv')
    
    # Quarterly time series for target drugs
    with engine.connect() as conn:
        quarterly = pd.read_sql("""
            SELECT drug_name, reaction, year, quarter, report_count
            FROM drug_reac_quarterly
            WHERE drug_name IN ('humira', 'zantac', 'jardiance')
            ORDER BY drug_name, reaction, year, quarter
        """, conn)
        
        demographics = pd.read_sql("""
            SELECT drug_name, reaction, sex, age_group, 
                   country, report_count
            FROM drug_reac_demo
            WHERE drug_name IN ('humira', 'zantac', 'jardiance')
        """, conn)
    
    quarterly['period'] = (quarterly['year'].astype(str) + 
                          '-Q' + quarterly['quarter'].astype(str))
    
    logger.info(f"Loaded {len(signals)} signals, "
                f"{len(quarterly)} quarterly rows, "
                f"{len(demographics)} demo rows")
    
    return signals, quarterly, demographics

def build_section1_overview(signals: pd.DataFrame) -> list:
    """
    Section 1 — Signal Overview
    KPI cards + ROR bar chart + confidence donut
    """
    figs = []
    
    # ── KPI Summary ───────────────────────────────────────
    high = signals[signals['confidence_label'] == 
                   'High — All three methods']
    
    kpi_fig = go.Figure()
    
    kpis = [
        ('Total Signals', len(signals), '#2196F3'),
        ('High Confidence', len(high), '#F44336'),
        ('Drugs Analyzed', signals['drug_name'].nunique(), '#4CAF50'),
        ('Quarters Analyzed', 20, '#FF9800')
    ]
    
    for i, (label, value, color) in enumerate(kpis):
        kpi_fig.add_trace(go.Indicator(
            mode="number",
            value=value,
            title={'text': label, 
                   'font': {'size': 14, 'color': COLORS['text']}},
            number={'font': {'size': 36, 'color': color}},
            domain={'x': [i*0.25, (i+1)*0.25], 'y': [0, 1]}
        ))
    
    kpi_fig.update_layout(
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['background'],
        height=150,
        margin=dict(l=20, r=20, t=20, b=20)
    )
    figs.append(('kpi', kpi_fig))
    
    # ── ROR Bar Chart ─────────────────────────────────────
    high_signals = signals[
        signals['confidence_label'] == 'High — All three methods'
    ].copy()
    high_signals = high_signals.sort_values('ROR', ascending=True)
    high_signals['label'] = (high_signals['drug_name'].str.upper() + 
                             ' — ' + 
                             high_signals['reaction'].str[:35])
    
    ror_fig = go.Figure()
    
    for drug in TARGET_DRUGS:
        subset = high_signals[high_signals['drug_name'] == drug]
        if subset.empty:
            continue
        ror_fig.add_trace(go.Bar(
            y=subset['label'],
            x=subset['ROR'],
            orientation='h',
            name=drug.capitalize(),
            marker_color=DRUG_COLORS.get(drug, '#888'),
            hovertemplate=(
                '<b>%{y}</b><br>'
                'ROR: %{x:.1f}<br>'
                '<extra></extra>'
            )
        ))
    
    ror_fig.update_layout(
        title=dict(
            text='High Confidence Signals — Reporting Odds Ratio',
            font=dict(color=COLORS['text'], size=16)
        ),
        paper_bgcolor=COLORS['background'],
        plot_bgcolor=COLORS['card'],
        font=dict(color=COLORS['text']),
        xaxis=dict(
            title='ROR (higher = stronger signal)',
            gridcolor=COLORS['grid'],
            type='log'   # log scale — zantac ROR 4851 vs humira 51
        ),
        yaxis=dict(gridcolor=COLORS['grid']),
        height=450,
        legend=dict(
            bgcolor=COLORS['card'],
            font=dict(color=COLORS['text'])
        ),
        margin=dict(l=300, r=50, t=60, b=50)
    )
    figs.append(('ror_bar', ror_fig))
    
    # ── Confidence Donut ──────────────────────────────────
    conf_counts = signals['confidence_label'].value_counts()
    
    donut_fig = go.Figure(go.Pie(
        labels=conf_counts.index,
        values=conf_counts.values,
        hole=0.5,
        marker_colors=[
            COLORS['high'], COLORS['medium'], COLORS['low']
        ],
        hovertemplate='%{label}<br>%{value} signals<extra></extra>'
    ))
    
    donut_fig.update_layout(
        title=dict(
            text='Signal Confidence Distribution',
            font=dict(color=COLORS['text'], size=16)
        ),
        paper_bgcolor=COLORS['background'],
        font=dict(color=COLORS['text']),
        height=400,
        legend=dict(
            bgcolor=COLORS['card'],
            font=dict(color=COLORS['text'])
        )
    )
    figs.append(('confidence_donut', donut_fig))
    
    return figs

def build_section2_timeseries(signals: pd.DataFrame,
                               quarterly: pd.DataFrame) -> list:
    """
    Section 2 — Time Series
    CUSUM-style trend charts for each high confidence signal
    """
    figs = []
    high = signals[
        signals['confidence_label'] == 'High — All three methods'
    ].head(6)  # top 6 for display
    
    for _, row in high.iterrows():
        drug = row['drug_name']
        reaction = row['reaction']
        ror = row['ROR']
        
        ts = quarterly[
            (quarterly['drug_name'] == drug) &
            (quarterly['reaction'] == reaction)
        ].copy()
        
        if ts.empty:
            continue
        
        fig = make_subplots(
            rows=1, cols=1,
            subplot_titles=[f'']
        )
        
        # Quarterly reports line
        fig.add_trace(go.Scatter(
            x=ts['period'],
            y=ts['report_count'],
            mode='lines+markers',
            name='Quarterly Reports',
            line=dict(
                color=DRUG_COLORS.get(drug, '#888'),
                width=2
            ),
            marker=dict(size=4),
            hovertemplate='%{x}<br>Reports: %{y:,}<extra></extra>'
        ))
        
        # Baseline mean line (2022 average)
        baseline = ts[ts['year'] == 2022]['report_count'].mean()
        if not pd.isna(baseline):
            fig.add_hline(
                y=baseline,
                line_dash='dash',
                line_color='#4CAF50',
                annotation_text=f'Baseline ({baseline:.0f})',
                annotation_font_color='#4CAF50'
            )
        
        fig.update_layout(
            title=dict(
                text=f'{drug.upper()} — {reaction}<br>'
                     f'<sup>ROR: {ror:.1f} | '
                     f'Confidence: High</sup>',
                font=dict(color=COLORS['text'], size=14)
            ),
            paper_bgcolor=COLORS['background'],
            plot_bgcolor=COLORS['card'],
            font=dict(color=COLORS['text']),
            xaxis=dict(
                gridcolor=COLORS['grid'],
                tickangle=45
            ),
            yaxis=dict(
                title='Quarterly Reports',
                gridcolor=COLORS['grid']
            ),
            height=350,
            showlegend=False,
            margin=dict(l=60, r=30, t=80, b=80)
        )
        
        figs.append((f'ts_{drug}_{reaction[:20]}', fig))
    
    return figs

def build_section3_demographics(demographics: pd.DataFrame,
                                 signals: pd.DataFrame) -> list:
    """
    Section 3 — Demographics
    Age and sex breakdown for each high confidence signal
    """
    figs = []
    high = signals[
        signals['confidence_label'] == 'High — All three methods'
    ]
    
    for _, row in high.iterrows():
        drug = row['drug_name']
        reaction = row['reaction']
        
        demo = demographics[
            (demographics['drug_name'] == drug) &
            (demographics['reaction'] == reaction)
        ]
        
        if demo.empty:
            continue
        
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=['By Sex', 'By Age Group']
        )
        
        # Sex breakdown
        sex_data = (demo[demo['sex'].isin(['M', 'F', 'U', 'NS'])]
                   .groupby('sex')['report_count']
                   .sum()
                   .reset_index())
        
        sex_colors = {
            'F': '#E91E63', 
            'M': '#2196F3',
            'U': '#9E9E9E', 
            'NS': '#607D8B'
        }
        
        fig.add_trace(go.Bar(
            x=sex_data['sex'],
            y=sex_data['report_count'],
            marker_color=[
                sex_colors.get(s, '#888') 
                for s in sex_data['sex']
            ],
            hovertemplate='%{x}: %{y:,}<extra></extra>'
        ), row=1, col=1)
        
        # Age breakdown
        age_order = ['0-17', '18-44', '45-64', '65+', 'Unknown']
        age_data = (demo.groupby('age_group')['report_count']
                   .sum()
                   .reindex(age_order)
                   .fillna(0)
                   .reset_index())
        
        fig.add_trace(go.Bar(
            x=age_data['age_group'],
            y=age_data['report_count'],
            marker_color=DRUG_COLORS.get(drug, '#888'),
            hovertemplate='%{x}: %{y:,}<extra></extra>'
        ), row=1, col=2)
        
        fig.update_layout(
            title=dict(
                text=f'{drug.upper()} — {reaction[:50]}',
                font=dict(color=COLORS['text'], size=14)
            ),
            paper_bgcolor=COLORS['background'],
            plot_bgcolor=COLORS['card'],
            font=dict(color=COLORS['text']),
            height=350,
            showlegend=False,
            margin=dict(l=60, r=30, t=80, b=60)
        )
        fig.update_xaxes(gridcolor=COLORS['grid'])
        fig.update_yaxes(gridcolor=COLORS['grid'])
        
        figs.append((f'demo_{drug}_{reaction[:20]}', fig))
    
    return figs

def build_section4_geographic(demographics: pd.DataFrame) -> list:
    """
    Section 4 — Geographic
    World map of report density by country
    """
    figs = []
    
    for drug in TARGET_DRUGS:
        drug_demo = demographics[
            demographics['drug_name'] == drug
        ]
        
        country_data = (drug_demo
                       .groupby('country')['report_count']
                       .sum()
                       .reset_index()
                       .sort_values('report_count', ascending=False))
        
        # Remove null/unknown countries
        country_data = country_data[
            country_data['country'].notna() &
            (country_data['country'] != '') &
            (country_data['country'] != 'Unknown')
        ]
        # Convert 2-letter codes to country names for plotly
        import pycountry
        def code_to_name(code):
            try:
                return pycountry.countries.get(alpha_2=code).name
            except:
                return None

        country_data['country_name'] = country_data['country'].apply(code_to_name)
        country_data = country_data.dropna(subset=['country_name'])
        # World map
        map_fig = go.Figure(go.Choropleth(
            locations=country_data['country_name'],
            locationmode='country names',
            z=country_data['report_count'],
            colorscale=[
                [0, '#1E2130'],
                [0.2, '#1565C0'],
                [0.5, '#1976D2'],
                [0.8, '#F44336'],
                [1.0, '#B71C1C']
            ],
            hovertemplate=(
                '<b>%{location}</b><br>'
                'Reports: %{z:,}<extra></extra>'
            ),
            colorbar=dict(
                title=dict(
                    text='Reports',
                    font=dict(color=COLORS['text'])
                ),
                tickfont=dict(color=COLORS['text'])
            )
        ))
        
        map_fig.update_layout(
            title=dict(
                text=f'{drug.upper()} — Global Report Density',
                font=dict(color=COLORS['text'], size=16)
            ),
            paper_bgcolor=COLORS['background'],
            geo=dict(
                bgcolor=COLORS['background'],
                lakecolor=COLORS['background'],
                landcolor='#2D3250',
                showland=True,
                showlakes=True,
                showocean=True,
                oceancolor=COLORS['background'],
                framecolor=COLORS['grid']
            ),
            font=dict(color=COLORS['text']),
            height=500,
            margin=dict(l=0, r=0, t=60, b=0)
        )
        figs.append((f'map_{drug}', map_fig))
        
        # Top 15 countries bar
        top15 = country_data.head(15)
        bar_fig = go.Figure(go.Bar(
            x=top15['report_count'],
            y=top15['country_name'],
            orientation='h',
            marker_color=DRUG_COLORS.get(drug, '#888'),
            hovertemplate='%{y}: %{x:,} reports<extra></extra>'
        ))
        
        bar_fig.update_layout(
            title=dict(
                text=f'{drug.upper()} — Top 15 Reporting Countries',
                font=dict(color=COLORS['text'], size=14)
            ),
            paper_bgcolor=COLORS['background'],
            plot_bgcolor=COLORS['card'],
            font=dict(color=COLORS['text']),
            xaxis=dict(
                title='Report Count',
                gridcolor=COLORS['grid']
            ),
            yaxis=dict(
                autorange='reversed',
                gridcolor=COLORS['grid']
            ),
            height=450,
            margin=dict(l=80, r=30, t=60, b=50)
        )
        figs.append((f'geo_bar_{drug}', bar_fig))
    
    return figs

def build_dashboard():
    """
    Master function — builds complete HTML dashboard.
    Combines all sections into one file.
    """
    import plotly.io as pio
    
    logger.info("Loading data...")
    signals, quarterly, demographics = load_data()
    
    logger.info("Building sections...")
    s1 = build_section1_overview(signals)
    s2 = build_section2_timeseries(signals, quarterly)
    s3 = build_section3_demographics(demographics, signals)
    s4 = build_section4_geographic(demographics)
    
    all_figs = s1 + s2 + s3 + s4
    
    # ── Build HTML ────────────────────────────────────────
    html_parts = []
    
    # Header
    html_parts.append(f"""
<!DOCTYPE html>
<html>
<head>
    <title>MedDrift — Pharmacovigilance Signal Detection</title>
    <style>
        body {{
            background-color: {COLORS['background']};
            color: {COLORS['text']};
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            padding: 30px 0 10px 0;
            border-bottom: 2px solid {COLORS['grid']};
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.2em;
            color: #2196F3;
            margin: 0;
            letter-spacing: 2px;
        }}
        .header p {{
            color: #888;
            margin: 8px 0 0 0;
            font-size: 1em;
        }}
        .section-title {{
            font-size: 1.4em;
            color: #2196F3;
            border-left: 4px solid #2196F3;
            padding-left: 15px;
            margin: 40px 0 20px 0;
        }}
        .chart-grid-2 {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .chart-grid-3 {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .chart-card {{
            background: {COLORS['card']};
            border-radius: 8px;
            padding: 10px;
            border: 1px solid {COLORS['grid']};
        }}
        .full-width {{
            margin-bottom: 20px;
        }}
        .methodology {{
            background: {COLORS['card']};
            border-radius: 8px;
            padding: 25px;
            margin: 20px 0;
            border: 1px solid {COLORS['grid']};
        }}
        .methodology h3 {{
            color: #2196F3;
            margin-top: 0;
        }}
        .method-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 20px;
        }}
        .method-card {{
            background: {COLORS['background']};
            border-radius: 6px;
            padding: 15px;
        }}
        .method-card h4 {{
            color: #FF9800;
            margin: 0 0 8px 0;
        }}
        .method-card p {{
            color: #aaa;
            font-size: 0.85em;
            margin: 0;
            line-height: 1.5;
        }}
        .footer {{
            text-align: center;
            color: #555;
            padding: 30px 0;
            border-top: 1px solid {COLORS['grid']};
            margin-top: 40px;
            font-size: 0.85em;
        }}
    </style>
</head>
<body>

<div class="header">
    <h1>⚕ MedDrift</h1>
    <p>Pharmacovigilance Signal Detection System &nbsp;|&nbsp; 
       FDA FAERS 2020–2024 &nbsp;|&nbsp; 
       30M+ Adverse Event Records</p>
</div>

<div class="methodology">
    <h3>Detection Methodology</h3>
    <div class="method-grid">
        <div class="method-card">
            <h4>Reporting Odds Ratio (ROR)</h4>
            <p>Measures disproportionate reporting of a 
            drug-reaction pair vs therapeutic class peers. 
            Signals flagged at ROR ≥ 5.0, p &lt; 0.05. 
            Class-stratified comparison eliminates 
            therapeutic class bias.</p>
        </div>
        <div class="method-card">
            <h4>CUSUM Control Charts</h4>
            <p>Detects sustained upward trends in quarterly 
            report counts. Standardized against fixed 2022 
            baseline. Accumulates deviations — resets on 
            negative. Alert threshold = 5.0σ.</p>
        </div>
        <div class="method-card">
            <h4>EWMA Smoothing</h4>
            <p>Exponentially Weighted Moving Average 
            (λ=0.2). Gives 80% weight to historical trend, 
            20% to current quarter. Alert when EWMA exceeds 
            baseline + 3σ. Sensitive to recent acceleration.</p>
        </div>
    </div>
</div>
""")

    # Section 1 — Overview
    html_parts.append('<div class="section-title">① Signal Overview</div>')
    
    for name, fig in s1:
        html_html = pio.to_html(fig, full_html=False,
                                include_plotlyjs='cdn'
                                if name == 'kpi' else False)
        if name == 'kpi':
            html_parts.append(
                f'<div class="full-width chart-card">{html_html}</div>'
            )
        elif name == 'ror_bar':
            html_parts.append(
                f'<div class="full-width chart-card">{html_html}</div>'
            )
        else:
            html_parts.append(
                f'<div class="full-width chart-card">{html_html}</div>'
            )

    # Section 2 — Time Series
    html_parts.append(
        '<div class="section-title">② Time Series Analysis</div>'
    )
    html_parts.append('<div class="chart-grid-2">')
    for name, fig in s2:
        fig_html = pio.to_html(fig, full_html=False, 
                               include_plotlyjs=False)
        html_parts.append(f'<div class="chart-card">{fig_html}</div>')
    html_parts.append('</div>')

    # Section 3 — Demographics
    html_parts.append(
        '<div class="section-title">③ Demographics Analysis</div>'
    )
    html_parts.append('<div class="chart-grid-2">')
    for name, fig in s3:
        fig_html = pio.to_html(fig, full_html=False,
                               include_plotlyjs=False)
        html_parts.append(f'<div class="chart-card">{fig_html}</div>')
    html_parts.append('</div>')

    # Section 4 — Geographic
    html_parts.append(
        '<div class="section-title">④ Geographic Distribution</div>'
    )
    for name, fig in s4:
        fig_html = pio.to_html(fig, full_html=False,
                               include_plotlyjs=False)
        if 'map_' in name:
            html_parts.append(
                f'<div class="full-width chart-card">{fig_html}</div>'
            )
        else:
            html_parts.append(
                f'<div class="full-width chart-card">{fig_html}</div>'
            )

    # Footer
    html_parts.append(f"""
<div class="footer">
    MedDrift &nbsp;|&nbsp; 
    Built with Python, MySQL, Plotly &nbsp;|&nbsp;
    Data: FDA FAERS Public Database &nbsp;|&nbsp;
    Statistical Methods: ROR, CUSUM, EWMA
</div>
</body>
</html>
""")

    # Save
    os.makedirs('outputs', exist_ok=True)
    output_path = 'outputs/dashboard.html'
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(''.join(html_parts))
    
    logger.info(f"Dashboard saved: {output_path}")
    print(f"\nDashboard ready: {output_path}")
    print("Open in any browser to view.")
    return output_path

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_dashboard()