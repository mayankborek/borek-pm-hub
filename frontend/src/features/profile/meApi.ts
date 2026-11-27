import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface MyProfile {
  id: string;
  name: string;
  email: string;
  role: string;
  job_title: string | null;
  phone: string | null;
  organisation: { id: string; name: string } | null;
}

export interface NotificationSetting {
  key: string;
  enabled: boolean;
}

export const MIN_PASSWORD_LENGTH = 12;

const keys = {
  profile: ['me', 'profile'] as const,
  settings: ['me', 'notification-settings'] as const,
};

/** GET /me/profile. */
export const useMyProfile = () => useQuery({ queryKey: keys.profile, queryFn: () => api<MyProfile>('/me/profile') });

/** PATCH /me/profile: the phone number is the only field a person can change; "" clears it. */
export function useUpdatePhone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (phone: string) => api<MyProfile>('/me/profile', { method: 'PATCH', body: JSON.stringify({ phone }) }),
    onSuccess: (profile) => qc.setQueryData(keys.profile, profile),
  });
}

/** GET /me/notification-settings: only the topics that apply to the signed-in role. */
export const useNotificationSettings = () =>
  useQuery({
    queryKey: keys.settings,
    queryFn: async () => (await api<{ settings: NotificationSetting[] }>('/me/notification-settings')).settings,
  });

/** PUT /me/notification-settings with the one key that changed; the list shows the change at once and rolls back on failure. */
export function useSetNotificationSetting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ key, enabled }: { key: string; enabled: boolean }) =>
      (await api<{ settings: NotificationSetting[] }>('/me/notification-settings', { method: 'PUT', body: JSON.stringify({ settings: { [key]: enabled } }) })).settings,
    onMutate: async ({ key, enabled }) => {
      await qc.cancelQueries({ queryKey: keys.settings });
      const before = qc.getQueryData<NotificationSetting[]>(keys.settings);
      qc.setQueryData<NotificationSetting[]>(keys.settings, (list) => list?.map((s) => (s.key === key ? { ...s, enabled } : s)));
      return { before };
    },
    onError: (_e, _v, ctx) => qc.setQueryData(keys.settings, ctx?.before),
    onSuccess: (settings) => qc.setQueryData(keys.settings, settings),
  });
}

/** POST /auth/change-password. Ends every session, this one included, so the caller signs out afterwards. */
export const useChangePassword = () =>
  useMutation({
    mutationFn: (input: { current_password: string; new_password: string }) =>
      api<void>('/auth/change-password', { method: 'POST', body: JSON.stringify(input) }),
  });

/** Labels for the notification keys the API can return. */
export const SETTING_COPY: Record<string, [string, string]> = {
  tasks_assigned: ['Tasks assigned to me', 'Assignments and changes, comments and files on tasks assigned to you.'],
  tasks_reported: ['Tasks I created', 'Changes, comments and files on tasks you created.'],
  mentions: ['Mentions', 'Someone mentions you in a comment.'],
  blocked_tasks: ['Blocked tasks', 'A task in your project was blocked.'],
  change_requests: ['Change requests', 'Updates on change requests.'],
  requirements: ['Requirements', 'Requirements and the client’s answers.'],
  reports: ['Project reports', 'New status reports shared by your project manager.'],
  milestones: ['Milestones', 'Changes to milestone dates and completion.'],
  projects: ['Projects', 'You were added to a project.'],
};
