import { Card, CardContent, Box, Chip } from "@mui/material";
import StorefrontIcon from "@mui/icons-material/Storefront";
import PhoneIcon from "@mui/icons-material/Phone";
import PlaceIcon from "@mui/icons-material/Place";
import VerifiedIcon from "@mui/icons-material/Verified";
import StarRoundedIcon from "@mui/icons-material/StarRounded";
import "../styles/productDetail.css";

export default function VendorInfoCard({ vendor }) {
  if (!vendor) return null;

  return (
    <Card className="vendor-info-card">
      <CardContent>
        <Box className="vendor-info-header">
          <StorefrontIcon />
          <h3>{vendor.shop_name}</h3>
          {vendor.is_verified && (
            <Chip
              icon={<VerifiedIcon />}
              label="Verified"
              size="small"
              color="success"
              className="vendor-verified-chip"
            />
          )}
        </Box>

        {vendor.rating_avg > 0 && (
          <Box className="vendor-info-row">
            <StarRoundedIcon fontSize="small" className="vendor-rating-icon" />
            <span>{vendor.rating_avg.toFixed(1)} / 5.0</span>
          </Box>
        )}

        <Box className="vendor-info-row">
          <PhoneIcon fontSize="small" />
          <span>{vendor.phone_number}</span>
        </Box>

        <Box className="vendor-info-row">
          <PlaceIcon fontSize="small" />
          <span>{vendor.shop_address}</span>
        </Box>

        {vendor.description && <p className="vendor-info-description">{vendor.description}</p>}
      </CardContent>
    </Card>
  );
}
