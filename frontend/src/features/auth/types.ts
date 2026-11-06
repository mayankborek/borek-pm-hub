export type Role = 'pm' | 'developer' | 'client' | 'admin' | 'account_manager';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}
