def normal_curve(upper_limit, digits=3):
    """Hampiri luas di bawah kurva Normal baku dari 0 hingga upper_limit.
         upper_limit  bilangan riil  Cari luas dari 0 hingga upper_limit.
    """
    mean, stddev = 0.0, 1.0
    area = numerical_integral((1/sqrt(2*pi) * e^(-0.5*((x-mean)/stddev)^2)),
                              0, upper_limit)    
    return(numerical_approx(area[0], digits=digits))
