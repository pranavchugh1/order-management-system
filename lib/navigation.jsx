'use client';
import NextLink from 'next/link';
import { useRouter, useParams as useNextParams, usePathname } from 'next/navigation';
import { useCallback, useEffect } from 'react';
export const Link = ({ to, children, ...props }) => <NextLink href={to} {...props}>{children}</NextLink>;
export const useNavigate = () => { const router = useRouter(); return useCallback((to, options) => typeof to === 'number' ? router.back() : options?.replace ? router.replace(to) : router.push(to), [router]); };
export const useParams = useNextParams;
export const useLocation = () => ({ pathname: usePathname(), state: null });
export const Navigate = ({ to }) => { const router = useRouter(); useEffect(() => { router.replace(to); }, [router, to]); return null; };
