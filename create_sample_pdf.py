import fitz  # type: ignore
import sys

def create_sample_pdf(filename="sample_invoice.pdf"):
    try:
        doc = fitz.open() # create new pdf
        page = doc.new_page()
        
        # Add some text that looks like an invoice
        text = """
        INVOICE
        Date: 2026-03-20
        From: Acme Corporation
        To: Smith Accounting
        Invoice #: INV-123456
        Reference: PO-98765
        
        Item 1: Professional Services - $500.00
        Item 2: Software License - $150.00
        Total: $650.00
        """
        rect = fitz.Rect(72, 72, 500, 500)
        page.insert_textbox(rect, text, fontsize=12)
        
        doc.save(filename)
        doc.close()
        print(f"Sample PDF created: {filename}")
    except Exception as e:
        print(f"Failed to create sample PDF: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    create_sample_pdf()
