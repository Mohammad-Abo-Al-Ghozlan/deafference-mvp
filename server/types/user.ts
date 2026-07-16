// types/user.ts
export interface CreateUserRequest {
  email: string;
  name?: string;
}

export interface UserResponse {
  id: number;
  email: string;
  name: string | null;
  createdAt: string;
  updatedAt: string;
}
