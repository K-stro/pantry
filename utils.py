import streamlit as st
from datetime import datetime
import pandas as pd

def format_price(price: float) -> str:
    """Format price with currency symbol"""
    return f"${price:.2f}"

def generate_product_card(product: pd.Series):
    """Generate a card-style display for a product"""
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        st.markdown(f"### {product['name']}")
        st.markdown(f"URL: [{product['url']}]({product['url']})")
    
    with col2:
        current_price = format_price(product['current_price'])
        st.markdown(f"**Current Price:** {current_price}")
        if product['alert_price'] > 0:
            alert_price = format_price(product['alert_price'])
            st.markdown(f"**Alert Price:** {alert_price}")
    
    with col3:
        last_updated = datetime.strptime(product['last_updated'], '%Y-%m-%d %H:%M:%S')
        st.markdown("**Last Updated:**")
        st.markdown(last_updated.strftime('%Y-%m-%d %H:%M'))
    
    st.markdown("---")
