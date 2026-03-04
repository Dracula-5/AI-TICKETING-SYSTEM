import axios from "axios";
import { getAuthItem } from "../utils/authSession";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_BASE_URL || "http://127.0.0.1:8000",
});

api.interceptors.request.use((config)=>{
    const token = getAuthItem("token");
    const tenant = getAuthItem("tenant_id");

    if(token){
        config.headers.Authorization = `Bearer ${token}`;
    }

    if(tenant){
        config.headers["X-Tenant-ID"] = tenant;
    }

  return config;
});

export default api;



