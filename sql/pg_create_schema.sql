-- PostgreSQL setup script
-- Run this after creating the database:
--   psql postgres -c "CREATE DATABASE salesdb;"
--   psql salesdb -f sql/pg_create_schema.sql

-- Drop existing tables if they exist
DROP TABLE IF EXISTS public.shipments;
DROP TABLE IF EXISTS public.inventory;
DROP TABLE IF EXISTS public.suppliers;

-- Suppliers
CREATE TABLE public.suppliers (
    supplier_id SERIAL PRIMARY KEY,
    supplier_name VARCHAR(100),
    country VARCHAR(50),
    contact_email VARCHAR(100)
);

-- Inventory
CREATE TABLE public.inventory (
    inventory_id SERIAL PRIMARY KEY,
    product_name VARCHAR(100),
    category VARCHAR(50),
    stock_quantity INT,
    unit_cost DECIMAL(10,2),
    supplier_id INT
);

-- Shipments
CREATE TABLE public.shipments (
    shipment_id SERIAL PRIMARY KEY,
    supplier_id INT,
    shipment_date DATE,
    expected_arrival DATE,
    status VARCHAR(50)
);

-- Sample data
INSERT INTO public.suppliers VALUES
(1, 'TechSupplies Co', 'USA', 'contact@techsupplies.com'),
(2, 'Global Parts Ltd', 'Germany', 'info@globalparts.de'),
(3, 'Asia Exports Inc', 'Japan', 'sales@asiaexports.jp');

INSERT INTO public.inventory VALUES
(1, 'Laptop', 'Electronics', 45, 750.00, 1),
(2, 'Monitor', 'Electronics', 30, 200.00, 1),
(3, 'Keyboard', 'Accessories', 100, 25.00, 2),
(4, 'Mouse', 'Accessories', 150, 15.00, 2),
(5, 'Desk Chair', 'Furniture', 20, 180.00, 3);

INSERT INTO public.shipments VALUES
(1, 1, '2024-01-10', '2024-01-20', 'delivered'),
(2, 2, '2024-02-05', '2024-02-15', 'in_transit'),
(3, 3, '2024-03-01', '2024-03-12', 'pending');

SELECT 'PostgreSQL schema and sample data created successfully!' AS status;
