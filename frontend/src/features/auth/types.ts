export type Role = 'pm' | 'developer' | 'client';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}
