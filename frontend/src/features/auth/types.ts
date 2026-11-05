export type Role = 'pm' | 'developer' | 'client' | 'admin';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}
