"""shopify-export-gap-filler.

Enrich Shopify exports with data the native CSV does not include:
rich order details, non-sensitive payment metadata, and abandoned checkouts.

GraphQL Admin API only. Read-only. No card / PCI data, ever.
"""

__version__ = "0.1.0"
