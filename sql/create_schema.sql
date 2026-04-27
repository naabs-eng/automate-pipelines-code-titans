-- Create database if not exists
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'SalesDB')
BEGIN
    CREATE DATABASE SalesDB;
END
GO

USE SalesDB;
GO

-- Drop existing tables if they exist
IF OBJECT_ID('dbo.OrderItems', 'U') IS NOT NULL
    DROP TABLE dbo.OrderItems;
IF OBJECT_ID('dbo.Orders', 'U') IS NOT NULL
    DROP TABLE dbo.Orders;
IF OBJECT_ID('dbo.Customers', 'U') IS NOT NULL
    DROP TABLE dbo.Customers;
IF OBJECT_ID('dbo.Products', 'U') IS NOT NULL
    DROP TABLE dbo.Products;

-- Create Products table
CREATE TABLE dbo.Products (
    ProductID INT PRIMARY KEY IDENTITY(1,1),
    ProductName NVARCHAR(100) NOT NULL,
    Category NVARCHAR(50) NOT NULL,
    UnitPrice DECIMAL(10, 2) NOT NULL
);

-- Create Customers table
CREATE TABLE dbo.Customers (
    CustomerID INT PRIMARY KEY IDENTITY(1,1),
    CustomerName NVARCHAR(100) NOT NULL,
    Email NVARCHAR(100),
    Country NVARCHAR(50) NOT NULL
);

-- Create Orders table
CREATE TABLE dbo.Orders (
    OrderID INT PRIMARY KEY IDENTITY(1,1),
    CustomerID INT NOT NULL,
    OrderDate DATETIME NOT NULL,
    FOREIGN KEY (CustomerID) REFERENCES dbo.Customers(CustomerID)
);

-- Create OrderItems table
CREATE TABLE dbo.OrderItems (
    OrderItemID INT PRIMARY KEY IDENTITY(1,1),
    OrderID INT NOT NULL,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (OrderID) REFERENCES dbo.Orders(OrderID),
    FOREIGN KEY (ProductID) REFERENCES dbo.Products(ProductID)
);

GO
PRINT 'Database schema created successfully!';
