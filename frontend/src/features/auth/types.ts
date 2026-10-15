export type Role = 'pm' | 'developer';

export interface User {
  id: string;
  name: string;
  email: string;
  role: Role;
}
