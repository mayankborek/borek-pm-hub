import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { fetchInvitation } from './clientAuthService';

/** The invitation named by `?invitation=` (or an explicit token), if there is one. */
export function useInvitation(explicitToken?: string) {
  const [params] = useSearchParams();
  const token = explicitToken ?? params.get('invitation');
  const query = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => fetchInvitation(token!),
    enabled: !!token,
    retry: false,
    staleTime: Infinity,
  });
  return { token, ...query };
}
