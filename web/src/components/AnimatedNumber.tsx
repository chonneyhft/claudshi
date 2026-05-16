import { motion, useSpring, useTransform } from "framer-motion";
import { useEffect } from "react";

type Props = {
  value: number;
  format?: (v: number) => string;
  duration?: number;
  className?: string;
};

export function AnimatedNumber({
  value,
  format = (v) => v.toFixed(2),
  className,
}: Props) {
  const spring = useSpring(value, { stiffness: 90, damping: 22, mass: 0.6 });
  const display = useTransform(spring, (v) => format(v));

  useEffect(() => {
    spring.set(value);
  }, [value, spring]);

  return <motion.span className={className}>{display}</motion.span>;
}
