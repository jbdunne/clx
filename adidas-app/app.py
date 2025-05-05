from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return """
    <html>
    <head>
        <title>Adidas Shoes App</title>
        <style>
            body { font-family: Arial; margin: 40px; }
            .shoe-card { border: 1px solid #ddd; padding: 15px; margin: 10px; display: inline-block; width: 200px; }
            button { margin: 5px; padding: 5px 10px; cursor: pointer; }
            .error { color: red; padding: 10px; display: none; }
        </style>
    </head>
    <body>
        <h1>Adidas Shoes Shop</h1>
        <div class="shoe-cards">
            <div class="shoe-card">
                <h3>Ultraboost 22</h3>
                <p>$180.00</p>
                <p>Responsive running shoes with Boost cushioning.</p>
                <button onclick="alert('Saved to wishlist')">Save</button>
                <button onclick="alert('Added to cart')">Add to Cart</button>
                <button onclick="alert('Proceeding to payment')">Pay Now</button>
            </div>
        </div>
        <div class="error" id="error">Please click on a shoe to perform actions</div>
        <script>
            document.body.addEventListener('click', function(e) {
                if (!e.target.closest('.shoe-card') && !e.target.closest('h1')) {
                    document.getElementById('error').style.display = 'block';
                    setTimeout(() => {
                        document.getElementById('error').style.display = 'none';
                    }, 2000);
                }
            });
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
