import pandas as pd
from datetime import datetime
from fpdf import FPDF
import plotly.graph_objects as go
import plotly.io as pio
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class DiagnosticReport:
    def __init__(self, pantry_manager, inventory_data):
        self.pantry_manager = pantry_manager
        self.inventory_data = inventory_data
        self.report_dir = Path("reports")
        self.report_dir.mkdir(exist_ok=True)

    def generate_inventory_chart(self):
        """Generate inventory status chart"""
        try:
            fig = go.Figure()
            for _, item in self.inventory_data.iterrows():
                fig.add_trace(go.Bar(
                    name=item['name'],
                    x=[item['name']],
                    y=[item['quantity']],
                    text=f"{(item['quantity']/item['capacity'])*100:.1f}%",
                    textposition='auto',
                ))
                fig.add_trace(go.Bar(
                    name=f"{item['name']} (Remaining)",
                    x=[item['name']],
                    y=[item['capacity'] - item['quantity']],
                    marker_color='lightgray'
                ))

            fig.update_layout(
                title="Inventory Levels",
                barmode='stack',
                showlegend=False,
                height=400
            )

            # Save as PNG for PDF inclusion
            chart_path = self.report_dir / "inventory_chart.png"
            fig.write_image(str(chart_path))
            return chart_path
        except Exception as e:
            logger.error(f"Error generating inventory chart: {e}")
            return None

    def generate_report(self):
        """Generate comprehensive diagnostic report"""
        try:
            # Initialize PDF
            pdf = FPDF()
            pdf.add_page()

            # Title
            pdf.set_font('Arial', 'B', 16)
            pdf.cell(0, 10, 'Smart Community Pantry - System Diagnostic Report', ln=True, align='C')
            pdf.set_font('Arial', '', 10)
            pdf.cell(0, 10, f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', ln=True, align='C')

            # System Overview
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(0, 10, 'System Overview', ln=True)
            pdf.set_font('Arial', '', 10)

            # Pantry Status
            pdf.cell(0, 10, 'Pantry Locations Status:', ln=True)
            locations = self.pantry_manager.get_all_locations()
            for _, pantry in locations.iterrows():
                status = self.pantry_manager.get_pantry_status(pantry['name'])
                if status:
                    pdf.cell(0, 5, f"• {pantry['name']}", ln=True)
                    pdf.cell(0, 5, f"  - Status: {'Open' if status['is_open'] else 'Closed'}", ln=True)
                    pdf.cell(0, 5, f"  - Inventory: {status['inventory_percentage']:.1f}% full", ln=True)
                    pdf.cell(0, 5, f"  - Services: {', '.join(status['services'])}", ln=True)
                    pdf.cell(0, 5, '', ln=True)

            # Inventory Status
            pdf.add_page()
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(0, 10, 'Inventory Status', ln=True)

            # Add inventory chart
            chart_path = self.generate_inventory_chart()
            if chart_path and chart_path.exists():
                pdf.image(str(chart_path), x=10, w=190)

            # Critical Items
            pdf.add_page()
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(0, 10, 'Critical Items', ln=True)
            pdf.set_font('Arial', '', 10)

            critical_items_found = False
            for _, item in self.inventory_data.iterrows():
                if item['quantity'] <= item['min_threshold']:
                    critical_items_found = True
                    pdf.cell(0, 5, f"• {item['name']}", ln=True)
                    pdf.cell(0, 5, f"  - Current: {item['quantity']} units", ln=True)
                    pdf.cell(0, 5, f"  - Minimum Threshold: {item['min_threshold']} units", ln=True)
                    pdf.cell(0, 5, '', ln=True)

            if not critical_items_found:
                pdf.cell(0, 5, "No critical items at this time.", ln=True)

            # System Health
            pdf.add_page()
            pdf.set_font('Arial', 'B', 14)
            pdf.cell(0, 10, 'System Health', ln=True)
            pdf.set_font('Arial', '', 10)

            # Storage Status
            total_capacity = sum(self.inventory_data['capacity'])
            total_inventory = sum(self.inventory_data['quantity'])
            utilization = (total_inventory / total_capacity) * 100 if total_capacity > 0 else 0

            pdf.cell(0, 5, 'Storage Utilization:', ln=True)
            pdf.cell(0, 5, f"• Total Capacity: {total_capacity} units", ln=True)
            pdf.cell(0, 5, f"• Current Total: {total_inventory} units", ln=True)
            pdf.cell(0, 5, f"• Utilization: {utilization:.1f}%", ln=True)
            pdf.cell(0, 5, '', ln=True)

            # Temperature and Humidity Status
            pdf.cell(0, 5, 'Environmental Conditions:', ln=True)
            for _, item in self.inventory_data.iterrows():
                if item['storage_condition'] == 'refrigerated':
                    temp_status = "🟢" if 2 <= item['temperature'] <= 6 else "🔴"
                else:
                    temp_status = "🟢" if 18 <= item['temperature'] <= 24 else "🔴"
                humidity_status = "🟢" if 40 <= item['humidity'] <= 60 else "🔴"

                pdf.cell(0, 5, f"• {item['name']}:", ln=True)
                pdf.cell(0, 5, f"  - Temperature: {temp_status} {item['temperature']:.1f}°C", ln=True)
                pdf.cell(0, 5, f"  - Humidity: {humidity_status} {item['humidity']:.1f}%", ln=True)
                pdf.cell(0, 5, '', ln=True)

            # Save report
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = self.report_dir / f"diagnostic_report_{timestamp}.pdf"
            pdf.output(str(report_path))

            # Cleanup temporary files
            if chart_path and chart_path.exists():
                chart_path.unlink()

            return report_path
        except Exception as e:
            logger.error(f"Error generating diagnostic report: {e}")
            return None