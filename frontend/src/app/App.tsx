import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/features/auth/AuthContext';
import { PrefsProvider } from '@/shared/prefs/PrefsContext';
import { router } from './router';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <PrefsProvider>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </PrefsProvider>
    </QueryClientProvider>
  );
}
