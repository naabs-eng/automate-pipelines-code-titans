USE SalesDB;
GO

-- Insert Products
INSERT INTO dbo.Products (ProductName, Category, UnitPrice) VALUES
('Laptop Pro', 'Electronics', 1299.99),
('Wireless Mouse', 'Electronics', 29.99),
('USB-C Cable', 'Accessories', 12.99),
('Monitor 4K', 'Electronics', 499.99),
('Keyboard Mechanical', 'Accessories', 149.99),
('Desk Lamp LED', 'Furniture', 59.99),
('Office Chair', 'Furniture', 299.99),
('Notebook A4', 'Stationery', 5.99),
('Pen Set', 'Stationery', 14.99),
('Headphones Wireless', 'Electronics', 199.99);

-- Insert Customers
INSERT INTO dbo.Customers (CustomerName, Email, Country) VALUES
('John Smith', 'john.smith@email.com', 'USA'),
('Sarah Johnson', 'sarah.j@email.com', 'USA'),
('Michael Brown', 'mbrown@email.com', 'Canada'),
('Emily Davis', 'emily.d@email.com', 'USA'),
('David Wilson', 'dwilson@email.com', 'UK'),
('Lisa Anderson', 'lander@email.com', 'USA'),
('James Taylor', 'jtaylor@email.com', 'Australia'),
('Jennifer White', 'jwhite@email.com', 'Canada'),
('Robert Lee', 'rlee@email.com', 'USA'),
('Maria Garcia', 'mgarcia@email.com', 'Mexico');

-- Insert Orders
INSERT INTO dbo.Orders (CustomerID, OrderDate) VALUES
(1, '2024-04-01 10:00:00'),
(2, '2024-04-02 14:30:00'),
(3, '2024-04-03 09:15:00'),
(1, '2024-04-05 11:45:00'),
(4, '2024-04-06 16:20:00'),
(5, '2024-04-08 08:30:00'),
(2, '2024-04-10 13:00:00'),
(6, '2024-04-12 10:15:00'),
(3, '2024-04-15 15:45:00'),
(7, '2024-04-18 12:00:00'),
(1, '2024-04-20 09:30:00'),
(8, '2024-04-22 14:15:00'),
(4, '2024-04-24 11:00:00'),
(9, '2024-04-25 16:45:00'),
(10, '2024-04-27 10:30:00');

-- Insert OrderItems
INSERT INTO dbo.OrderItems (OrderID, ProductID, Quantity, UnitPrice) VALUES
(1, 1, 1, 1299.99),
(1, 2, 2, 29.99),
(2, 4, 1, 499.99),
(2, 5, 1, 149.99),
(3, 3, 5, 12.99),
(3, 10, 1, 199.99),
(4, 7, 1, 299.99),
(4, 9, 3, 14.99),
(5, 2, 3, 29.99),
(5, 8, 10, 5.99),
(6, 1, 1, 1299.99),
(6, 6, 2, 59.99),
(7, 5, 2, 149.99),
(7, 3, 4, 12.99),
(8, 4, 1, 499.99),
(9, 10, 2, 199.99),
(9, 9, 5, 14.99),
(10, 1, 1, 1299.99),
(11, 2, 1, 29.99),
(11, 6, 3, 59.99),
(12, 7, 1, 299.99),
(13, 3, 8, 12.99),
(14, 5, 1, 149.99),
(14, 10, 1, 199.99),
(15, 4, 2, 499.99);

GO
PRINT 'Sample data inserted successfully!';
SELECT * FROM dbo.Products;
SELECT * FROM dbo.Customers;
SELECT * FROM dbo.Orders;
SELECT * FROM dbo.OrderItems;
