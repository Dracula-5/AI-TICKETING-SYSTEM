import { useEffect, useState } from "react";
import {
  Grid,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Box,
  Pagination,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import SearchOffRoundedIcon from "@mui/icons-material/SearchOffRounded";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import ProductCardSkeleton from "../components/ProductCardSkeleton";
import { listProducts } from "../api/products";
import { MARKETPLACE_CATEGORIES as CATEGORIES } from "../constants/marketplaceCategories";
import "../styles/marketplace.css";
import { useToast } from "../context/ToastContext";

const SKELETON_COUNT = 8;

const PAGE_SIZE = 12;

export default function Marketplace() {
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("newest");
  const [loading, setLoading] = useState(false);
  const toast = useToast();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    listProducts({
      search: search || undefined,
      category: category || undefined,
      sort,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setProducts(res.data.items || []);
        setTotal(res.data.total || 0);
      })
      .catch(() => {
        if (!cancelled) {
          setProducts([]);
          setTotal(0);
          toast.error("Couldn't load products. Please try again.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, category, sort, page]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <Navbar />
      <Sidebar role={localStorage.getItem("role")} />

      <div className="marketplace-main">
        <div className="marketplace-header">
          <h1>Marketplace</h1>
          <p>Browse products from local vendors</p>
        </div>

        <Box className="marketplace-filters">
          <TextField
            placeholder="Search products..."
            value={search}
            onChange={(e) => {
              setPage(1);
              setSearch(e.target.value);
            }}
            className="marketplace-search"
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: "#999" }} />
                </InputAdornment>
              ),
            }}
          />

          <FormControl className="marketplace-filter-select">
            <InputLabel>Category</InputLabel>
            <Select
              value={category}
              label="Category"
              onChange={(e) => {
                setPage(1);
                setCategory(e.target.value);
              }}
            >
              <MenuItem value="">All Categories</MenuItem>
              {CATEGORIES.map((c) => (
                <MenuItem key={c} value={c}>{c}</MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl className="marketplace-filter-select">
            <InputLabel>Sort By</InputLabel>
            <Select
              value={sort}
              label="Sort By"
              onChange={(e) => {
                setPage(1);
                setSort(e.target.value);
              }}
            >
              <MenuItem value="newest">Newest</MenuItem>
              <MenuItem value="price_asc">Price: Low to High</MenuItem>
              <MenuItem value="price_desc">Price: High to Low</MenuItem>
              <MenuItem value="popular">Most Popular</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {loading ? (
          <Grid container spacing={3}>
            {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
              // eslint-disable-next-line react/no-array-index-key
              <Grid item xs={12} sm={6} md={4} lg={3} key={i}>
                <ProductCardSkeleton />
              </Grid>
            ))}
          </Grid>
        ) : products.length === 0 ? (
          <Box className="marketplace-empty">
            <SearchOffRoundedIcon sx={{ fontSize: 48, color: "var(--muted)", mb: 1 }} />
            <p>No products found. Try adjusting your search or filters.</p>
          </Box>
        ) : (
          <>
            <Grid container spacing={3}>
              {products.map((p) => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={p.id}>
                  <ProductCard product={p} />
                </Grid>
              ))}
            </Grid>

            <Box className="marketplace-pagination">
              <Pagination
                count={pageCount}
                page={page}
                onChange={(_, value) => setPage(value)}
                color="primary"
              />
            </Box>
          </>
        )}
      </div>
      <Footer />
    </>
  );
}
