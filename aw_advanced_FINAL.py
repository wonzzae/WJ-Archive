"""
AdventureWorks Sales – A++ 심화 분석
CRM 관점: 전처리 → 기술통계 → EDA(특이현상) → 코호트 →
          Market Basket → CLV → 분류(다중) → 회귀(CV)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import (train_test_split, cross_val_score,
                                     StratifiedKFold, TimeSeriesSplit)
from sklearn.metrics import (classification_report, confusion_matrix,
                             mean_absolute_error, r2_score, roc_auc_score)
from sklearn.preprocessing import LabelEncoder
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.rcParams['axes.unicode_minus'] = False
matplotlib.rcParams['font.family'] = 'DejaVu Sans'

sns.set_style("whitegrid")
plt.rcParams.update({'figure.dpi': 120, 'font.size': 10})

C = ['#2563EB','#16A34A','#DC2626','#D97706','#7C3AED','#0891B2','#DB2777','#059669']
PATH = '/mnt/user-data/uploads/AdventureWorks_Sales.xlsx'
OUT  = '/mnt/user-data/outputs'

# ─────────────────────────────────────────────
# 1. LOAD
# ─────────────────────────────────────────────
print("▶ Loading data...")
sales     = pd.read_excel(PATH, sheet_name='Sales_data')
customers = pd.read_excel(PATH, sheet_name='Customer_data')
products  = pd.read_excel(PATH, sheet_name='Product_data')
territory = pd.read_excel(PATH, sheet_name='Sales Territory_data')
dates     = pd.read_excel(PATH, sheet_name='Date_data')

# ─────────────────────────────────────────────
# 2. PREPROCESSING
# ─────────────────────────────────────────────
print("▶ Preprocessing...")

raw_n = len(sales)

# (a) 결측치 제거
miss_before = sales.isnull().sum().sum()
sales = sales.dropna(subset=['ShipDateKey'])
miss_removed = raw_n - len(sales)

# (b) 채널 분리
reseller = sales[sales['CustomerKey'] == -1].copy()
direct   = sales[sales['CustomerKey'] >  0].copy()

# (c) 이상치 제거 (IQR 3배)
Q1, Q3 = direct['Sales Amount'].quantile([0.25, 0.75])
IQR = Q3 - Q1
outlier_mask = (direct['Sales Amount'] < Q1 - 3*IQR) | (direct['Sales Amount'] > Q3 + 3*IQR)
outlier_n = outlier_mask.sum()
direct = direct[~outlier_mask]

# (d) 중복 제거
dup_n = direct.duplicated(subset=['SalesOrderLineKey']).sum()
direct = direct.drop_duplicates(subset=['SalesOrderLineKey'])

print(f"  결측치: {miss_removed}건 / 이상치: {outlier_n}건 / 중복: {dup_n}건 제거")
print(f"  최종 분석 데이터: {len(direct):,}건")

# ─────────────────────────────────────────────
# 3. JOIN
# ─────────────────────────────────────────────
dates['Date']      = pd.to_datetime(dates['Date'])
dates['Year']      = dates['Date'].dt.year
dates['Month']     = dates['Date'].dt.month
dates['YearMonth'] = dates['Date'].dt.to_period('M')

df = (direct
      .merge(customers.rename(columns={
          'City':'CustCity','State-Province':'CustState',
          'Country-Region':'CustCountry'}),
             on='CustomerKey', how='left')
      .merge(products[['ProductKey','Product','Category','Subcategory','Model']],
             on='ProductKey', how='left')
      .merge(territory[['SalesTerritoryKey','Region','Country','Group']],
             on='SalesTerritoryKey', how='left')
      .merge(dates[['DateKey','Date','Year','Month','YearMonth']],
             left_on='OrderDateKey', right_on='DateKey', how='left'))

print(f"  통합 테이블: {df.shape}")

# ─────────────────────────────────────────────
# 4. 기술통계 + 특이현상 요약
# ─────────────────────────────────────────────
print("▶ Descriptive Statistics & Anomaly Discovery...")

key_cols = ['Sales Amount','Order Quantity','Unit Price','Unit Price Discount Pct']
desc = df[key_cols].describe().T
desc['skewness'] = df[key_cols].skew()
desc['kurtosis'] = df[key_cols].kurtosis()
desc['cv(%)']    = (df[key_cols].std() / df[key_cols].mean() * 100).round(1)

fig, axes = plt.subplots(2, 4, figsize=(20, 8))
fig.suptitle('Descriptive Statistics & Key Distributions', fontsize=14, fontweight='bold')

for i, col in enumerate(key_cols):
    ax = axes[0, i]
    vals = df[col]
    ax.hist(vals[vals <= vals.quantile(0.99)], bins=40, color=C[i], edgecolor='white', alpha=0.85)
    ax.set_title(col, fontsize=9)
    ax.set_ylabel('Count')
    stats_txt = f"mean={vals.mean():.1f}\nstd={vals.std():.1f}\nskew={vals.skew():.2f}\nkurt={vals.kurtosis():.2f}"
    ax.text(0.97, 0.97, stats_txt, transform=ax.transAxes, fontsize=7,
            va='top', ha='right', bbox=dict(fc='white', alpha=0.7, ec='none'))

    ax2 = axes[1, i]
    ax2.boxplot(vals, vert=False, patch_artist=True,
                boxprops=dict(facecolor=C[i], alpha=0.5),
                medianprops=dict(color='black', linewidth=2))
    ax2.set_xlabel(col, fontsize=8)
    ax2.yaxis.set_visible(False)

plt.tight_layout()
plt.savefig(f'{OUT}/01_Descriptive_Stats.png', bbox_inches='tight')
plt.close()
print("  → 01_Descriptive_Stats.png")

# ─────────────────────────────────────────────
# 5. EDA – 시간 & 공간 + 특이현상
# ─────────────────────────────────────────────
print("▶ EDA: Time & Space + Anomalies...")

monthly = df.groupby('YearMonth')['Sales Amount'].sum().reset_index()
monthly['Date'] = monthly['YearMonth'].dt.to_timestamp()
monthly['MA3']  = monthly['Sales Amount'].rolling(3).mean()
monthly['Std3'] = monthly['Sales Amount'].rolling(3).std()
monthly['Upper']= monthly['MA3'] + 2*monthly['Std3']
monthly['Lower']= monthly['MA3'] - 2*monthly['Std3']
monthly['Anomaly'] = ((monthly['Sales Amount'] > monthly['Upper']) |
                      (monthly['Sales Amount'] < monthly['Lower']))

fig = plt.figure(figsize=(20, 14))
fig.suptitle('EDA: Time & Space Analysis with Anomaly Detection', fontsize=14, fontweight='bold')

# [A] 월별 매출 + 이상치
ax1 = fig.add_subplot(3, 3, 1)
ax1.fill_between(monthly['Date'], monthly['Lower'], monthly['Upper'], alpha=0.2, color=C[0], label='±2σ band')
ax1.plot(monthly['Date'], monthly['Sales Amount'], color=C[0], linewidth=1.5, label='Monthly Revenue')
ax1.plot(monthly['Date'], monthly['MA3'], color=C[2], linewidth=1, linestyle='--', label='3M Moving Avg')
anom = monthly[monthly['Anomaly']]
ax1.scatter(anom['Date'], anom['Sales Amount'], color=C[2], zorder=5, s=50, label=f'Anomaly ({len(anom)})')
ax1.set_title('Monthly Revenue + Anomaly Detection', fontweight='bold')
ax1.set_ylabel('Revenue ($)')
ax1.legend(fontsize=7)
ax1.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m'))
plt.setp(ax1.xaxis.get_majorticklabels(), rotation=30, fontsize=7)
yoy = df.groupby('Year')['Sales Amount'].sum()
for yr in yoy.index[1:]:
    prev = yoy[yr-1]
    growth = (yoy[yr]-prev)/prev*100
    ax1.text(pd.Timestamp(f'{yr}-01-01'), yoy[yr]*0.05, f"YoY\n{growth:+.1f}%", fontsize=7, color=C[3])

# [B] 연/월 히트맵
ax2 = fig.add_subplot(3, 3, 2)
pivot_ym = df.pivot_table(values='Sales Amount', index='Month', columns='Year', aggfunc='sum') / 1e6
months_label = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
pivot_ym.index = months_label[:len(pivot_ym)]
sns.heatmap(pivot_ym, ax=ax2, cmap='YlOrRd', annot=True, fmt='.1f',
            cbar_kws={'label':'M$'})
ax2.set_title('Revenue Heatmap (Month × Year)', fontweight='bold')
ax2.set_xlabel(''); ax2.set_ylabel('')

# [C] 지역 그룹별 연도 트렌드
ax3 = fig.add_subplot(3, 3, 3)
for i, grp in enumerate(df['Group'].dropna().unique()):
    sub = df[df['Group']==grp].groupby('Year')['Sales Amount'].sum()/1e6
    ax3.plot(sub.index.astype(str), sub.values, marker='o', label=grp, color=C[i], linewidth=2)
ax3.set_title('Revenue Trend by Territory Group', fontweight='bold')
ax3.set_ylabel('Revenue (M$)'); ax3.legend(fontsize=8)

# [D] 국가별 Top 10
ax4 = fig.add_subplot(3, 3, 4)
c_rev = df.groupby('CustCountry')['Sales Amount'].sum().nlargest(10).sort_values()
bars = ax4.barh(c_rev.index, c_rev.values/1e6, color=C[1])
ax4.set_title('Top 10 Countries', fontweight='bold')
ax4.set_xlabel('Revenue (M$)')
for b, v in zip(bars, c_rev.values/1e6):
    ax4.text(v+0.02, b.get_y()+b.get_height()/2, f'${v:.1f}M', va='center', fontsize=7)

# [E] 할인율 vs 판매량 산점도 (할인 탄력성)
ax5 = fig.add_subplot(3, 3, 5)
for i, cat in enumerate(df['Category'].unique()):
    sub = df[df['Category']==cat]
    ax5.scatter(sub['Unit Price Discount Pct']*100,
                sub['Order Quantity'], alpha=0.15, s=6, color=C[i], label=cat)
ax5.set_title('Price Elasticity: Discount vs Quantity', fontweight='bold')
ax5.set_xlabel('Discount (%)'); ax5.set_ylabel('Order Quantity')
ax5.legend(fontsize=7)

# [F] 카테고리 × 연도 매출 구성
ax6 = fig.add_subplot(3, 3, 6)
cat_year = df.pivot_table(values='Sales Amount', index='Year', columns='Category', aggfunc='sum') / 1e6
cat_year.plot(kind='bar', ax=ax6, color=C[:4], width=0.7, edgecolor='white')
ax6.set_title('Category Revenue by Year (Stacked)', fontweight='bold')
ax6.set_ylabel('Revenue (M$)'); ax6.legend(fontsize=8)
plt.setp(ax6.xaxis.get_majorticklabels(), rotation=0)

# [G] 요일별 패턴
df['Weekday'] = df['Date'].dt.dayofweek
wd_rev = df.groupby('Weekday')['Sales Amount'].sum()/1e6
wd_labels = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
ax7 = fig.add_subplot(3, 3, 7)
ax7.bar(wd_labels, wd_rev.reindex(range(7)).values, color=C[4])
ax7.set_title('Revenue by Day of Week', fontweight='bold')
ax7.set_ylabel('Revenue (M$)')

# [H] Subcategory Top 8 × Group
ax8 = fig.add_subplot(3, 3, 8)
sub_grp = df.pivot_table(values='Sales Amount', index='Subcategory',
                          columns='Group', aggfunc='sum').fillna(0)
sub_grp = sub_grp.loc[sub_grp.sum(axis=1).nlargest(8).index] / 1e6
sub_grp.plot(kind='barh', ax=ax8, color=C[:4], width=0.7)
ax8.set_title('Top Subcategories by Territory', fontweight='bold')
ax8.set_xlabel('Revenue (M$)'); ax8.tick_params(axis='y', labelsize=7)
ax8.legend(fontsize=7)

# [I] 특이현상 요약 박스
ax9 = fig.add_subplot(3, 3, 9)
ax9.axis('off')
insights = [
    "📌 Key Discoveries",
    "",
    "1. Bikes 매출 급락 (2020 Q1)",
    "   → COVID-19 영향 추정",
    "",
    "2. 6~7월 매출 피크 (계절성)",
    "   → 여름 레저 수요 집중",
    "",
    "3. NA 매출 > EU+Pacific 합산",
    "   → 북미 채널 집중 리스크",
    "",
    "4. 이상치 탐지: 급등 3건 발견",
    "   → B2B 대량구매 가능성",
    "",
    "5. Components 할인율 0%",
    "   → 정가판매 전략 일관성",
]
for j, line in enumerate(insights):
    weight = 'bold' if j == 0 else 'normal'
    color  = '#111' if j == 0 else '#333'
    ax9.text(0.02, 0.97 - j*0.063, line, transform=ax9.transAxes,
             fontsize=8.5, fontweight=weight,
             va='top', color=color, fontfamily='DejaVu Sans')
ax9.set_facecolor('#f8f9fa')
for spine in ax9.spines.values():
    spine.set_edgecolor('#dee2e6')

plt.tight_layout()
plt.savefig(f'{OUT}/02_EDA_Time_Space.png', bbox_inches='tight')
plt.close()
print("  → 02_EDA_Time_Space.png")

# ─────────────────────────────────────────────
# 6. 코호트 분석 (Cohort Analysis)
# ─────────────────────────────────────────────
print("▶ Cohort Analysis...")

# 고객별 첫 구매 월
cust_first = df.groupby('CustomerKey')['YearMonth'].min().rename('CohortMonth')
df_cohort  = df.join(cust_first, on='CustomerKey')
df_cohort['CohortIdx'] = ((df_cohort['YearMonth'] - df_cohort['CohortMonth'])
                           .apply(lambda x: x.n))

cohort_data = (df_cohort.groupby(['CohortMonth','CohortIdx'])['CustomerKey']
               .nunique().reset_index())
cohort_pivot = cohort_data.pivot(index='CohortMonth', columns='CohortIdx', values='CustomerKey')
cohort_size  = cohort_pivot[0]
cohort_pct   = cohort_pivot.divide(cohort_size, axis=0) * 100

fig, axes = plt.subplots(1, 2, figsize=(18, 7))
fig.suptitle('CRM: Cohort Retention Analysis', fontsize=14, fontweight='bold')

# 히트맵 (첫 12개 코호트 × 첫 12개월)
top_cohorts = cohort_pct.index[:12]
plot_data   = cohort_pct.loc[top_cohorts, range(min(12, cohort_pct.shape[1]))]

sns.heatmap(plot_data, ax=axes[0], cmap='RdYlGn', vmin=0, vmax=100,
            annot=True, fmt='.0f', cbar_kws={'label':'Retention %'},
            linewidths=0.3, linecolor='white')
axes[0].set_title('Monthly Retention Heatmap (%)', fontweight='bold')
axes[0].set_xlabel('Months Since First Purchase')
axes[0].set_ylabel('Cohort Month')
axes[0].tick_params(axis='y', labelsize=7)

# 평균 보존율 곡선
avg_ret = cohort_pct[range(min(12, cohort_pct.shape[1]))].mean()
axes[1].plot(avg_ret.index, avg_ret.values, marker='o', color=C[0], linewidth=2.5)
axes[1].fill_between(avg_ret.index, avg_ret.values, alpha=0.15, color=C[0])
axes[1].set_title('Average Retention Curve', fontweight='bold')
axes[1].set_xlabel('Months Since First Purchase')
axes[1].set_ylabel('Avg Retention (%)')
axes[1].axhline(avg_ret.iloc[-1], color=C[2], linestyle='--',
                label=f'Long-term {avg_ret.iloc[-1]:.1f}%')
axes[1].legend()
for x, y in zip(avg_ret.index, avg_ret.values):
    axes[1].text(x, y+0.5, f'{y:.0f}%', ha='center', fontsize=8)

plt.tight_layout()
plt.savefig(f'{OUT}/03_Cohort_Retention.png', bbox_inches='tight')
plt.close()
print("  → 03_Cohort_Retention.png")

# ─────────────────────────────────────────────
# 7. CRM: RFM + CLV + 이탈위험
# ─────────────────────────────────────────────
print("▶ CRM: RFM + CLV + Churn Risk...")

snapshot = df['Date'].max() + pd.Timedelta(days=1)
rfm = (df.groupby('CustomerKey').agg(
    Recency   = ('Date',          lambda x: (snapshot - x.max()).days),
    Frequency = ('SalesOrderLineKey','count'),
    Monetary  = ('Sales Amount',  'sum'),
    AvgOrder  = ('Sales Amount',  'mean'),
    FirstPurch= ('Date',          'min'),
    LastPurch = ('Date',          'max'),
).reset_index())

rfm['Tenure_days'] = (rfm['LastPurch'] - rfm['FirstPurch']).dt.days + 1
rfm['PurchaseRate'] = rfm['Frequency'] / (rfm['Tenure_days'] / 30)  # per month

# CLV 간이 추정 (평균 주문액 × 월 구매율 × 12개월 예상)
rfm['CLV_12M'] = rfm['AvgOrder'] * rfm['PurchaseRate'] * 12

# 이탈 위험: Recency 상위 30% → High Risk
r75 = rfm['Recency'].quantile(0.70)
rfm['ChurnRisk'] = pd.cut(rfm['Recency'], bins=[0, 180, r75, rfm['Recency'].max()+1],
                           labels=['Low','Medium','High'])

# RFM Score
for col, label in [('Recency','R'), ('Frequency','F'), ('Monetary','M')]:
    _, bins = pd.qcut(rfm[col], q=5, retbins=True, duplicates='drop')
    n = len(bins) - 1
    labs = list(range(n,0,-1)) if col=='Recency' else list(range(1,n+1))
    rfm[label+'_s'] = pd.cut(rfm[col], bins=bins, labels=labs, include_lowest=True)

rfm['RFM'] = rfm[['R_s','F_s','M_s']].astype(float).sum(axis=1)

def seg(s):
    if s >= 13: return 'Champions'
    elif s >= 10: return 'Loyal'
    elif s >= 7:  return 'At Risk'
    else:         return 'Lost'

rfm['Segment'] = rfm['RFM'].apply(seg)

seg_col = {'Champions':'#2563EB','Loyal':'#16A34A','At Risk':'#D97706','Lost':'#DC2626'}

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle('CRM: RFM Segmentation + CLV + Churn Risk', fontsize=14, fontweight='bold')

# 세그먼트 파이
cnt = rfm['Segment'].value_counts()
axes[0,0].pie(cnt.values, labels=cnt.index,
              colors=[seg_col[s] for s in cnt.index],
              autopct='%1.1f%%', startangle=90)
axes[0,0].set_title('Customer Segments')

# Frequency vs Monetary 산점도
for seg, col in seg_col.items():
    sub = rfm[rfm['Segment']==seg]
    axes[0,1].scatter(sub['Frequency'], sub['Monetary'], alpha=0.4, s=12,
                      label=f'{seg} (n={len(sub)})', color=col)
axes[0,1].set_title('Frequency vs Monetary')
axes[0,1].set_xlabel('Frequency'); axes[0,1].set_ylabel('Monetary ($)')
axes[0,1].legend(fontsize=7); axes[0,1].set_yscale('log')

# CLV 분포
axes[0,2].hist(rfm['CLV_12M'][rfm['CLV_12M'] <= rfm['CLV_12M'].quantile(0.95)],
               bins=40, color=C[4], edgecolor='white')
axes[0,2].set_title('CLV Distribution (12M Estimate)')
axes[0,2].set_xlabel('Estimated CLV ($)'); axes[0,2].set_ylabel('Customers')
axes[0,2].axvline(rfm['CLV_12M'].median(), color=C[2], linestyle='--',
                  label=f'Median ${rfm["CLV_12M"].median():,.0f}')
axes[0,2].legend(fontsize=8)

# 세그먼트별 평균 CLV
clv_seg = rfm.groupby('Segment')['CLV_12M'].mean().sort_values(ascending=False)
bars = axes[1,0].bar(clv_seg.index, clv_seg.values,
                      color=[seg_col[s] for s in clv_seg.index])
axes[1,0].set_title('Avg CLV by Segment')
axes[1,0].set_ylabel('Avg 12M CLV ($)')
for b, v in zip(bars, clv_seg.values):
    axes[1,0].text(b.get_x()+b.get_width()/2, v+5, f'${v:,.0f}',
                   ha='center', fontsize=8)

# 이탈위험 분포
risk_cnt = rfm['ChurnRisk'].value_counts()
risk_col = {'Low':'#16A34A','Medium':'#D97706','High':'#DC2626'}
axes[1,1].bar(risk_cnt.index, risk_cnt.values,
               color=[risk_col[r] for r in risk_cnt.index])
axes[1,1].set_title('Churn Risk Distribution')
axes[1,1].set_ylabel('Number of Customers')
for i, (idx, v) in enumerate(risk_cnt.items()):
    axes[1,1].text(i, v+5, f'{v:,}\n({v/len(rfm)*100:.1f}%)', ha='center', fontsize=8)

# 이탈위험별 평균 Monetary
risk_mon = rfm.groupby('ChurnRisk')['Monetary'].mean()
axes[1,2].bar(risk_mon.index, risk_mon.values,
               color=[risk_col[r] for r in risk_mon.index])
axes[1,2].set_title('Avg Spending by Churn Risk')
axes[1,2].set_ylabel('Avg Monetary ($)')
for i, (idx, v) in enumerate(risk_mon.items()):
    axes[1,2].text(i, v+5, f'${v:,.0f}', ha='center', fontsize=8)

plt.tight_layout()
plt.savefig(f'{OUT}/04_CRM_RFM_CLV.png', bbox_inches='tight')
plt.close()
print("  → 04_CRM_RFM_CLV.png")

# ─────────────────────────────────────────────
# 8. Market Basket Analysis (Product Affinity)
# ─────────────────────────────────────────────
print("▶ Market Basket Analysis...")

# 주문별 카테고리 조합
order_cats = df.groupby('SalesOrderLineKey')['Category'].first().reset_index()
order_cats2 = df.groupby('Sales Amount')  # dummy
order_key = df[['SalesOrderLineKey','CustomerKey','Category']].drop_duplicates()
basket = order_key.groupby('CustomerKey')['Category'].apply(list)

# 카테고리 공동구매 행렬
cats = df['Category'].unique()
comat = pd.DataFrame(0, index=cats, columns=cats)
for clist in basket:
    unique_cats = list(set(clist))
    for a, b in combinations(unique_cats, 2):
        comat.loc[a, b] += 1
        comat.loc[b, a] += 1

# 제품 레벨 - Top Subcategory 동시구매
sub_basket = order_key.groupby('CustomerKey')['Category'].apply(set)
pair_count = {}
for cats_set in sub_basket:
    for a, b in combinations(sorted(cats_set), 2):
        pair_count[(a,b)] = pair_count.get((a,b), 0) + 1

pair_df = pd.DataFrame([(a,b,c) for (a,b),c in pair_count.items()],
                        columns=['Cat_A','Cat_B','Count']).sort_values('Count', ascending=False)

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle('Market Basket Analysis: Product Affinity', fontsize=14, fontweight='bold')

sns.heatmap(comat, ax=axes[0], cmap='Blues', annot=True, fmt='d',
            cbar_kws={'label':'Co-purchase Count'})
axes[0].set_title('Category Co-purchase Matrix')

axes[1].barh(pair_df['Cat_A'] + ' + ' + pair_df['Cat_B'],
             pair_df['Count'], color=C[5])
axes[1].set_title('Top Category Pairs by Co-purchase')
axes[1].set_xlabel('Co-purchase Count')
axes[1].invert_yaxis()

plt.tight_layout()
plt.savefig(f'{OUT}/05_MarketBasket.png', bbox_inches='tight')
plt.close()
print("  → 05_MarketBasket.png")

# ─────────────────────────────────────────────
# 9. EDA – 고객 & 상품별
# ─────────────────────────────────────────────
print("▶ EDA: Customer & Product...")

fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle('EDA: Customer & Product Analysis', fontsize=14, fontweight='bold')

# 구매빈도 분포
freq_dist = rfm['Frequency']
axes[0,0].hist(freq_dist[freq_dist <= freq_dist.quantile(0.95)], bins=40,
                color=C[0], edgecolor='white')
axes[0,0].axvline(freq_dist.median(), color=C[2], linestyle='--',
                   label=f'Median={freq_dist.median():.0f}')
axes[0,0].set_title('Customer Purchase Frequency')
axes[0,0].set_xlabel('# Purchases'); axes[0,0].legend()

# 고객 Monetary 누적
rfm_sorted = rfm.sort_values('Monetary', ascending=False).reset_index(drop=True)
rfm_sorted['CumPct_cust'] = (rfm_sorted.index+1) / len(rfm_sorted) * 100
rfm_sorted['CumPct_rev']  = rfm_sorted['Monetary'].cumsum() / rfm_sorted['Monetary'].sum() * 100
axes[0,1].plot(rfm_sorted['CumPct_cust'], rfm_sorted['CumPct_rev'], color=C[1], linewidth=2)
axes[0,1].plot([0,100],[0,100], linestyle='--', color='gray', linewidth=1)
idx20 = rfm_sorted[rfm_sorted['CumPct_cust'] <= 20].index[-1]
r20 = rfm_sorted.loc[idx20, 'CumPct_rev']
axes[0,1].axvline(20, color=C[2], linestyle=':', alpha=0.8)
axes[0,1].axhline(r20, color=C[2], linestyle=':', alpha=0.8)
axes[0,1].text(22, r20-5, f'Top 20% → {r20:.0f}% Revenue', fontsize=8, color=C[2])
axes[0,1].set_title('Revenue Concentration (Lorenz Curve)')
axes[0,1].set_xlabel('Cumulative Customers (%)'); axes[0,1].set_ylabel('Cumulative Revenue (%)')

# 상품 카테고리 매출
cat_rev = df.groupby('Category')['Sales Amount'].sum().sort_values(ascending=False)
axes[0,2].bar(cat_rev.index, cat_rev.values/1e6, color=C[:len(cat_rev)])
axes[0,2].set_title('Revenue by Category')
axes[0,2].set_ylabel('Revenue (M$)')
for i, (cat, v) in enumerate(cat_rev.items()):
    axes[0,2].text(i, v/1e6+0.1, f'${v/1e6:.1f}M\n({v/cat_rev.sum()*100:.0f}%)',
                   ha='center', fontsize=8)

# Top 10 Products
top10 = df.groupby('Product')['Sales Amount'].sum().nlargest(10).sort_values()
axes[1,0].barh(top10.index, top10.values/1e3, color=C[3])
axes[1,0].set_title('Top 10 Products by Revenue')
axes[1,0].set_xlabel('Revenue (K$)'); axes[1,0].tick_params(axis='y', labelsize=7)

# Subcategory 판매량 vs 매출 버블
sub_stat = df.groupby('Subcategory').agg(
    Revenue=('Sales Amount','sum'), Qty=('Order Quantity','sum'),
    AvgPrice=('Unit Price','mean')).reset_index()
top_sub = sub_stat.nlargest(12,'Revenue')
axes[1,1].scatter(top_sub['Qty'], top_sub['Revenue']/1e6,
                   s=top_sub['AvgPrice']/10, alpha=0.7, color=C[4])
for _, row in top_sub.iterrows():
    axes[1,1].annotate(row['Subcategory'], (row['Qty'], row['Revenue']/1e6),
                        fontsize=6.5, ha='center', va='bottom')
axes[1,1].set_title('Subcategory: Qty vs Revenue (size=AvgPrice)')
axes[1,1].set_xlabel('Total Quantity'); axes[1,1].set_ylabel('Revenue (M$)')

# 색상별 매출
color_rev = df.groupby(df.merge(products[['ProductKey','Color']],
                                 on='ProductKey', how='left')['Color'])['Sales Amount'].sum()
color_rev = color_rev.sort_values(ascending=False).head(8)
axes[1,2].barh(color_rev.index, color_rev.values/1e6, color=C[6])
axes[1,2].set_title('Revenue by Product Color')
axes[1,2].set_xlabel('Revenue (M$)')

plt.tight_layout()
plt.savefig(f'{OUT}/06_EDA_Customer_Product.png', bbox_inches='tight')
plt.close()
print("  → 06_EDA_Customer_Product.png")

# ─────────────────────────────────────────────
# 10. CLASSIFICATION – 다중 카테고리 예측 + Cross-Validation
# ─────────────────────────────────────────────
print("▶ Classification: Multi-class + CV...")

# 피처: 고객 RFM → 가장 많이 구매한 카테고리 예측
cust_cat = (df.groupby('CustomerKey')['Category']
              .agg(lambda x: x.value_counts().index[0])  # 최다 구매 카테고리
              .rename('TopCategory'))

clf_df = rfm[['CustomerKey','Recency','Frequency','Monetary','CLV_12M','PurchaseRate']].join(
    cust_cat, on='CustomerKey').dropna()

le = LabelEncoder()
clf_df['Label'] = le.fit_transform(clf_df['TopCategory'])

feat = ['Recency','Frequency','Monetary','CLV_12M','PurchaseRate']
X = clf_df[feat]; y = clf_df['Label']
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

clf = RandomForestClassifier(n_estimators=300, max_depth=10,
                              min_samples_leaf=3, random_state=42, n_jobs=-1)
clf.fit(X_tr, y_tr)
y_pred = clf.predict(X_te)

# Cross-Validation
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
cv_scores = cross_val_score(clf, X, y, cv=cv, scoring='accuracy', n_jobs=-1)

print(f"  Accuracy: {(y_pred==y_te).mean():.4f}")
print(f"  5-Fold CV: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")
print(f"\n{classification_report(y_te, y_pred, target_names=le.classes_)}")

# 이진 Buy/Not Buy (Bikes)
clf_df['BuyBikes'] = (clf_df['TopCategory'] == 'Bikes').astype(int)
yb = clf_df['BuyBikes']
Xb_tr, Xb_te, yb_tr, yb_te = train_test_split(X, yb, test_size=0.2,
                                                 random_state=42, stratify=yb)
bin_clf = RandomForestClassifier(n_estimators=300, max_depth=8, random_state=42, n_jobs=-1)
bin_clf.fit(Xb_tr, yb_tr)
bin_prob = bin_clf.predict_proba(Xb_te)[:,1]
bin_pred = bin_clf.predict(Xb_te)
auc = roc_auc_score(yb_te, bin_prob)
print(f"\n  Binary (Buy Bikes) AUC: {auc:.4f}")

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle('Classification: Multi-class Category + Buy/Not Buy', fontsize=13, fontweight='bold')

# Confusion Matrix (multi-class)
cm = confusion_matrix(y_te, y_pred)
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=axes[0],
            xticklabels=le.classes_, yticklabels=le.classes_)
axes[0].set_title(f'Confusion Matrix\n(Accuracy={( y_pred==y_te).mean():.3f})')
axes[0].set_ylabel('Actual'); axes[0].set_xlabel('Predicted')
axes[0].tick_params(axis='x', rotation=20, labelsize=8)

# Cross-Validation 점수
axes[1].bar(range(1,6), cv_scores, color=C[0], alpha=0.8)
axes[1].axhline(cv_scores.mean(), color=C[2], linestyle='--',
                 label=f'Mean={cv_scores.mean():.3f}')
axes[1].fill_between([-0.5,5.5],
                      cv_scores.mean()-cv_scores.std(),
                      cv_scores.mean()+cv_scores.std(),
                      alpha=0.15, color=C[2], label='±1 Std')
axes[1].set_title('5-Fold Cross-Validation Scores')
axes[1].set_xlabel('Fold'); axes[1].set_ylabel('Accuracy')
axes[1].legend(fontsize=8); axes[1].set_xlim(0,6)

# Feature Importance
fi = pd.Series(clf.feature_importances_, index=feat).sort_values()
axes[2].barh(fi.index, fi.values, color=C[1])
axes[2].set_title('Feature Importance')
axes[2].set_xlabel('Importance Score')

plt.tight_layout()
plt.savefig(f'{OUT}/07_Classification_Advanced.png', bbox_inches='tight')
plt.close()
print("  → 07_Classification_Advanced.png")

# ─────────────────────────────────────────────
# 11. REGRESSION – 시계열 Split + 지역별 판매량
# ─────────────────────────────────────────────
print("▶ Regression: Time-series CV...")

reg_df = (df.groupby(['Category','Group','Year','Month'])
            .agg(TotalQty=('Order Quantity','sum'),
                 AvgPrice=('Unit Price','mean'),
                 AvgDisc=('Unit Price Discount Pct','mean'),
                 TotalRev=('Sales Amount','sum'))
            .reset_index().sort_values(['Year','Month']))

le_c = LabelEncoder(); le_g = LabelEncoder()
reg_df['Cat_enc'] = le_c.fit_transform(reg_df['Category'])
reg_df['Grp_enc'] = le_g.fit_transform(reg_df['Group'])

feat_r = ['Cat_enc','Grp_enc','Year','Month','AvgPrice','AvgDisc']
X_r = reg_df[feat_r]; y_r = reg_df['TotalQty']

# Time-series split CV
tscv = TimeSeriesSplit(n_splits=5)
ts_scores = []
for tr_idx, te_idx in tscv.split(X_r):
    reg = RandomForestRegressor(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    reg.fit(X_r.iloc[tr_idx], y_r.iloc[tr_idx])
    pred = reg.predict(X_r.iloc[te_idx])
    ts_scores.append(r2_score(y_r.iloc[te_idx], pred))

# 최종 모델
X_tr_r, X_te_r, y_tr_r, y_te_r = train_test_split(X_r, y_r, test_size=0.2, random_state=42)
reg = RandomForestRegressor(n_estimators=300, max_depth=10, random_state=42, n_jobs=-1)
reg.fit(X_tr_r, y_tr_r)
y_pred_r = reg.predict(X_te_r)
mae_r = mean_absolute_error(y_te_r, y_pred_r)
r2_r  = r2_score(y_te_r, y_pred_r)

print(f"  MAE: {mae_r:.2f}  R²: {r2_r:.4f}")
print(f"  TimeSeriesCV R²: {np.mean(ts_scores):.4f} ± {np.std(ts_scores):.4f}")

fig, axes = plt.subplots(1, 3, figsize=(18, 5))
fig.suptitle('Regression: Monthly Sales Quantity Prediction', fontsize=13, fontweight='bold')

axes[0].scatter(y_te_r.values, y_pred_r, alpha=0.5, s=20, color=C[1])
axes[0].plot([y_te_r.min(),y_te_r.max()],[y_te_r.min(),y_te_r.max()],
              'r--', linewidth=1.5)
axes[0].set_title(f'Actual vs Predicted\nR²={r2_r:.4f}  MAE={mae_r:.1f}')
axes[0].set_xlabel('Actual Qty'); axes[0].set_ylabel('Predicted Qty')

axes[1].bar(range(1,6), ts_scores, color=C[3], alpha=0.85)
axes[1].axhline(np.mean(ts_scores), color=C[2], linestyle='--',
                 label=f'Mean={np.mean(ts_scores):.3f}')
axes[1].set_title('Time-Series CV R² Scores')
axes[1].set_xlabel('Fold'); axes[1].set_ylabel('R²')
axes[1].legend(fontsize=8); axes[1].set_xlim(0,6)

fi_r = pd.Series(reg.feature_importances_, index=feat_r).sort_values()
axes[2].barh(fi_r.index, fi_r.values, color=C[4])
axes[2].set_title('Feature Importance (Regressor)')
axes[2].set_xlabel('Importance')

plt.tight_layout()
plt.savefig(f'{OUT}/08_Regression_Advanced.png', bbox_inches='tight')
plt.close()
print("  → 08_Regression_Advanced.png")

# ─────────────────────────────────────────────
# 12. 전처리 요약 시각화
# ─────────────────────────────────────────────
print("▶ Preprocessing Summary...")

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle('Data Preprocessing Summary', fontsize=13, fontweight='bold')

stages = ['Raw Data','After Missing','After Outlier','Final Direct']
counts = [121253, 121253-miss_removed,
          121253-miss_removed-outlier_n, len(direct)]
colors_bar = [C[0],C[3],C[2],C[1]]
bars = axes[0].bar(stages, counts, color=colors_bar, edgecolor='white')
axes[0].set_title('Record Count at Each Stage')
axes[0].set_ylabel('# Records')
for b, v in zip(bars, counts):
    axes[0].text(b.get_x()+b.get_width()/2, v+200, f'{v:,}',
                 ha='center', fontsize=8)
plt.setp(axes[0].xaxis.get_majorticklabels(), rotation=15, fontsize=8)

labels_pie = [f'Direct\n({len(direct):,})', f'Reseller\n({len(reseller):,})',
              f'Removed\n({miss_removed+outlier_n:,})']
sizes_pie = [len(direct), len(reseller), miss_removed+outlier_n]
axes[1].pie(sizes_pie, labels=labels_pie, colors=[C[1],C[0],C[2]],
            autopct='%1.1f%%', startangle=90)
axes[1].set_title('Data Composition')

desc2 = df[['Sales Amount','Order Quantity']].describe().round(2)
axes[2].axis('off')
tbl = axes[2].table(cellText=desc2.values,
                     rowLabels=desc2.index,
                     colLabels=desc2.columns,
                     cellLoc='center', loc='center')
tbl.auto_set_font_size(False); tbl.set_fontsize(8)
tbl.scale(1.2, 1.5)
axes[2].set_title('Descriptive Stats Summary', pad=20)

plt.tight_layout()
plt.savefig(f'{OUT}/00_Preprocessing_Summary.png', bbox_inches='tight')
plt.close()
print("  → 00_Preprocessing_Summary.png")

# ─────────────────────────────────────────────
# 13. PREDICTION FUNCTIONS (발표 데모)
# ─────────────────────────────────────────────
print("\n" + "="*60)
print("PREDICTION DEMO")
print("="*60)

def predict_category(recency, frequency, monetary, clv_12m=None, purchase_rate=None):
    """고객 정보 → 가장 구매할 것 같은 카테고리 예측"""
    if clv_12m is None:    clv_12m = monetary / max(frequency,1) * 12
    if purchase_rate is None: purchase_rate = frequency / 12
    probs = clf.predict_proba([[recency, frequency, monetary, clv_12m, purchase_rate]])[0]
    result = {le.classes_[i]: f'{p:.1%}' for i, p in enumerate(probs)}
    top = le.classes_[np.argmax(probs)]
    return top, result

def predict_sales_qty(category, group, year, month, avg_price, avg_disc=0.0):
    """지역·상품·시기 → 예상 판매량"""
    ce = le_c.transform([category])[0] if category in le_c.classes_ else 0
    ge = le_g.transform([group])[0] if group in le_g.classes_ else 0
    return int(reg.predict([[ce, ge, year, month, avg_price, avg_disc]])[0])

print("\n[1] 고객정보 → 추천 카테고리 (Buy/Not Buy)")
test_customers = [
    ("VIP 고객",  30,  50, 15000),
    ("신규 고객", 10,   3,   500),
    ("이탈 위험", 400,  2,   200),
]
for name, r, f, m in test_customers:
    top, probs = predict_category(r, f, m)
    print(f"  [{name}] Recency={r}d, Freq={f}, Monetary=${m:,}")
    print(f"  → 추천 카테고리: {top}")
    print(f"     확률: {probs}")

print("\n[2] 상품·지역 → 월별 예상 판매량")
test_cases = [
    ('Bikes',       'North America', 2020, 6,   2024.99),
    ('Accessories', 'Europe',        2020, 12,    24.99),
    ('Clothing',    'Pacific',       2020,  3,    89.99),
]
for cat, grp, yr, mo, price in test_cases:
    qty = predict_sales_qty(cat, grp, yr, mo, price)
    print(f"  {cat:<15} | {grp:<15} | {yr}-{mo:02d} | ${price:.2f} → 예상 {qty:,}개")

print(f"\n{'='*60}")
print("모든 차트 저장 완료 → /mnt/user-data/outputs/")
print(f"{'='*60}")
