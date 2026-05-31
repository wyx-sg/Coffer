import { RouterProvider } from "react-router-dom";
import { ToastProvider } from "./components/ui/toast";
import { router } from "./router";

export default function App() {
  // ToastProvider wraps the router so every route (and the mutation hooks they
  // drive) can surface failures through useToast(); its <Toaster/> renders once.
  return (
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  );
}
