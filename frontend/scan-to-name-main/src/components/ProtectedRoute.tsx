import { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { isAuthenticated } from "@/lib/api";

export const ProtectedRoute = ({ children }: { children: ReactNode }) => {
  if (!isAuthenticated()) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};
