"""UCI Online Retail -> cleaned invoice lines with RFM scores per customer, for Tableau."""
import pandas as pd
import datetime as dt
import urllib.request
import os

# Stock codes that are not products: postage, carriage, manual adjustments,
# discounts, bank charges and charity donations
NON_PRODUCT_CODES = ['POST', 'DOT', 'M', 'm', 'C2', 'D', 'CRUK', 'BANK CHARGES', 'PADS', 'AMAZONFEE', 'B', 'S']


def download_data():
    """Download the workbook next to this script; skipped if it is already there."""
    print("Downloading UCI dataset...")
    url = 'https://archive.ics.uci.edu/ml/machine-learning-databases/00352/Online%20Retail.xlsx'

    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_name = os.path.join(current_dir, 'Online_Retail.xlsx')

    if not os.path.exists(file_name):
        urllib.request.urlretrieve(url, file_name)
    print(f"Dataset available at: {file_name}")
    return file_name


def process_data(file_name):
    """Clean the invoice lines, score every customer with RFM quartiles and export the CSV."""
    print("Loading data (this may take a minute)...")
    df = pd.read_excel(file_name)
    print(f"Raw invoice lines: {len(df):,}")

    print("Cleaning data...")
    # 1. Remove lines without CustomerID (sales that cannot be attributed to a customer)
    df = df.dropna(subset=['CustomerID'])

    # 2. Remove exact duplicate lines (the same product line recorded twice)
    df = df.drop_duplicates()

    # 3. Keep real products with a positive price
    df = df[(df['UnitPrice'] > 0) & (~df['StockCode'].astype(str).isin(NON_PRODUCT_CODES))]

    # 4. Keep cancellations (invoices starting with "C") as negative revenue:
    #    dropping them would keep purchases that were later returned
    is_cancellation = df['InvoiceNo'].astype(str).str.startswith('C')

    # 5. Net revenue per line (negative for cancellations)
    df['TotalSales'] = df['Quantity'] * df['UnitPrice']

    # 6. CustomerID is read as float because of the NaNs: back to an integer label
    df['CustomerID'] = df['CustomerID'].astype(int).astype(str)
    print(f"Clean lines: {len(df):,} (of which {is_cancellation.sum():,} cancellation lines)")

    print("Calculating RFM Metrics...")
    # Recency is measured from the day after the last transaction, not from today
    analysis_date = df['InvoiceDate'].max() + dt.timedelta(days=1)

    # Recency and Frequency come from purchases only (a cancellation is not a visit);
    # Monetary comes from every line, so returns are netted out
    purchases = df[~is_cancellation]
    rfm = purchases.groupby('CustomerID').agg(
        Recency=('InvoiceDate', lambda x: (analysis_date - x.max()).days),
        Frequency=('InvoiceNo', 'nunique')
    )
    rfm['Monetary'] = df.groupby('CustomerID')['TotalSales'].sum().round(2)

    # Only customers who bought something and kept a positive net spend can be scored
    rfm = rfm[rfm['Monetary'] > 0].reset_index()
    print(f"Customers segmented: {len(rfm):,}")

    # Quartile scores, 4 = best. Recency is reversed: fewer days since the last purchase is better
    r_labels = range(4, 0, -1)
    f_labels = range(1, 5)
    m_labels = range(1, 5)

    rfm['R_Score'] = pd.qcut(rfm['Recency'], q=4, labels=r_labels)
    # Frequency and Monetary have many ties; rank(method='first') breaks them so qcut can
    # always build four bins instead of failing on duplicate edges
    rfm['F_Score'] = pd.qcut(rfm['Frequency'].rank(method='first'), q=4, labels=f_labels)
    rfm['M_Score'] = pd.qcut(rfm['Monetary'].rank(method='first'), q=4, labels=m_labels)

    rfm['RFM_Segment'] = rfm['R_Score'].astype(str) + rfm['F_Score'].astype(str) + rfm['M_Score'].astype(str)
    rfm['RFM_Score'] = rfm[['R_Score', 'F_Score', 'M_Score']].astype(int).sum(axis=1)

    # Segments on the summed score (3-12)
    def assign_segment(score):
        if score >= 10: return 'Champions'
        elif score >= 8: return 'Loyal Customers'
        elif score >= 6: return 'Potential Loyal Customers'
        elif score >= 4: return 'At Risk'
        else: return 'Lost'

    rfm['Customer_Profile'] = rfm['RFM_Score'].apply(assign_segment)

    # Join RFM to the transactions of scored customers (transaction and client level together)
    final_df = df.merge(rfm, on='CustomerID', how='inner')

    print("Exporting clean data for Tableau...")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    final_df.to_csv(os.path.join(current_dir, 'ecommerce_cleaned_rfm.csv'), index=False)
    print("Process completed successfully! File 'ecommerce_cleaned_rfm.csv' ready.")


if __name__ == "__main__":
    file = download_data()
    process_data(file)
