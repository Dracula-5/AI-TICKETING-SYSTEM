import { Card, CardMedia, CardContent, CardActions, Button, Chip, Box, IconButton, Tooltip } from "@mui/material";
import StorefrontIcon from "@mui/icons-material/Storefront";
import VerifiedIcon from "@mui/icons-material/Verified";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import AddShoppingCartIcon from "@mui/icons-material/AddShoppingCart";
import { Link } from "react-router-dom";
import { useCart } from "../context/CartContext";
import "../styles/marketplace.css";

const PLACEHOLDER_IMAGE = "https://placehold.co/400x300?text=No+Image";

export default function ProductCard({ product }) {
  const image = product.images?.[0]?.url || PLACEHOLDER_IMAGE;
  const { addItem } = useCart();

  return (
    <Card className="product-card">
      <CardMedia
        component="img"
        image={image}
        alt={product.title}
        className="product-card-media"
      />
      <CardContent className="product-card-content">
        <h4 className="product-card-title">{product.title}</h4>

        <Box className="product-card-price-row">
          <span className="product-card-price">
            {product.currency} {product.price.toLocaleString()}
          </span>
          {product.category && (
            <Chip label={product.category} size="small" className="product-card-category" />
          )}
        </Box>

        <Box className="product-card-vendor">
          <StorefrontIcon fontSize="small" />
          <span>{product.vendor?.shop_name}</span>
          {product.vendor?.is_verified && (
            <VerifiedIcon fontSize="small" className="product-card-verified" titleAccess="Verified vendor" />
          )}
          {product.vendor?.rating_avg > 0 && (
            <span className="product-card-rating">
              <StarRoundedIcon fontSize="small" /> {product.vendor.rating_avg.toFixed(1)}
            </span>
          )}
        </Box>

        <p className="product-card-stock">
          {product.stock_quantity > 0 ? `${product.stock_quantity} in stock` : "Out of stock"}
        </p>
      </CardContent>
      <CardActions className="product-card-actions">
        <Button
          fullWidth
          variant="contained"
          component={Link}
          to={`/product/${product.id}`}
        >
          View Details
        </Button>
        {product.stock_quantity > 0 && (
          <Tooltip title="Add to Cart">
            <IconButton
              color="primary"
              onClick={(e) => {
                e.preventDefault();
                addItem(product, 1);
              }}
              aria-label="Add to cart"
            >
              <AddShoppingCartIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </CardActions>
    </Card>
  );
}
