import pandas as pd
import logging
from sqlalchemy import create_engine
from config import DB_CONFIG

logger = logging.getLogger(__name__)

def get_engine():
    url = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )
    return create_engine(url)

def get_demographics(drug_name: str, reaction: str) -> dict:
    """
    Returns age and sex breakdown for a drug-reaction pair.
    Queries pre-computed drug_reac_demo materialized view.
    """
    engine = get_engine()
    
    query = """
        SELECT sex, age_group, country, report_count
        FROM drug_reac_demo
        WHERE drug_name = %(drug)s
        AND reaction = %(reaction)s
    """
    
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, 
                        params={'drug': drug_name, 
                                'reaction': reaction})
    
    if df.empty:
        return {}
    
    # Sex breakdown
    sex_breakdown = (df.groupby('sex')['report_count']
                     .sum()
                     .sort_values(ascending=False)
                     .to_dict())
    
    # Age breakdown
    age_order = ['0-17', '18-44', '45-64', '65+', 'Unknown']
    age_breakdown = (df.groupby('age_group')['report_count']
                     .sum()
                     .reindex(age_order)
                     .fillna(0)
                     .to_dict())
    
    # Top 5 countries
    country_breakdown = (df.groupby('country')['report_count']
                         .sum()
                         .sort_values(ascending=False)
                         .head(5)
                         .to_dict())
    
    return {
        'drug': drug_name,
        'reaction': reaction,
        'sex': sex_breakdown,
        'age_group': age_breakdown,
        'top_countries': country_breakdown,
        'total_reports': df['report_count'].sum()
    }

def analyze_all_signals(signals_path: str = 'outputs/master_signals.csv'):
    """
    Runs demographics for all high-confidence signals.
    Saves results and generates charts.
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import os
    
    os.makedirs('outputs/demographics', exist_ok=True)
    
    signals = pd.read_csv(signals_path)
    high_conf = signals[
        signals['confidence_label'] == 'High — All three methods'
    ]
    
    logger.info(f"Running demographics for {len(high_conf)} high-confidence signals")
    
    all_results = []
    
    for _, row in high_conf.iterrows():
        drug = row['drug_name']
        reaction = row['reaction']
        
        demo = get_demographics(drug, reaction)
        if not demo:
            continue
        
        all_results.append(demo)
        
        # Plot demographics
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle(f'{drug.upper()} — {reaction[:40]}', 
                    fontsize=12, fontweight='bold')
        
        # Sex chart
        sex_data = {k: v for k, v in demo['sex'].items() 
                   if k in ['M', 'F', 'U', 'NS']}
        if sex_data:
            axes[0].bar(sex_data.keys(), sex_data.values(), 
                       color=['steelblue', 'coral', 'gray', 'lightgray'])
            axes[0].set_title('By Sex')
            axes[0].set_ylabel('Reports')
        
        # Age chart
        age_data = {k: v for k, v in demo['age_group'].items() 
                   if v > 0}
        if age_data:
            axes[1].bar(age_data.keys(), age_data.values(),
                       color='steelblue')
            axes[1].set_title('By Age Group')
            axes[1].tick_params(axis='x', rotation=45)
        
        # Country chart
        if demo['top_countries']:
            countries = list(demo['top_countries'].keys())
            counts = list(demo['top_countries'].values())
            axes[2].barh(countries, counts, color='steelblue')
            axes[2].set_title('Top 5 Countries')
        
        plt.tight_layout()
        safe_name = (f"{drug}_{reaction[:25].replace(' ', '_')}"
                    .replace('/', '_'))
        plt.savefig(f'outputs/demographics/{safe_name}.png',
                   dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Demographics saved: {drug} | {reaction}")
    
    return all_results

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = analyze_all_signals()
    
    print("\nDEMOGRAPHICS SUMMARY")
    print("="*60)
    for r in results:
        print(f"\n{r['drug'].upper()} — {r['reaction']}")
        print(f"  Total reports: {r['total_reports']:,}")
        print(f"  Sex: {r['sex']}")
        print(f"  Age: {r['age_group']}")
        print(f"  Top countries: {r['top_countries']}")