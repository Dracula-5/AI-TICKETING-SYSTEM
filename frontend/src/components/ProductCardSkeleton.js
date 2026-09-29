import { Card, CardContent, Skeleton } from "@mui/material";
import "../styles/marketplace.css";

export default function ProductCardSkeleton() {
  return (
    <Card className="product-card">
      <Skeleton variant="rectangular" className="product-card-media" height={180} />
      <CardContent className="product-card-content">
        <Skeleton variant="text" width="80%" height={28} />
        <Skeleton variant="text" width="40%" height={24} sx={{ mb: 1 }} />
        <Skeleton variant="text" width="60%" />
        <Skeleton variant="text" width="30%" />
      </CardContent>
    </Card>
  );
}
